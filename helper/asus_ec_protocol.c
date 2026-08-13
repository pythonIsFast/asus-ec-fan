#define _POSIX_C_SOURCE 200809L

#include "asus_ec_protocol.h"

#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <sys/io.h>
#include <time.h>

#define OBF_BIT 0x01
#define IBF_BIT 0x02
#define TIMEOUT_NS 200000000L
#define POLL_NS 50000L
#define MAX_POLL_ATTEMPTS (TIMEOUT_NS / POLL_NS)
#define MAX_DRAIN_BYTES 64

static bool io_open;

static void poll_pause(void) {
    const struct timespec delay = {.tv_sec = 0, .tv_nsec = POLL_NS};
    (void)nanosleep(&delay, NULL);
}

static asus_ec_result wait_for_status(uint8_t mask, bool set,
                                      asus_ec_result timeout_error) {
    for (long attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt++) {
        const bool is_set = (inb(ASUS_EC_COMMAND_PORT) & mask) != 0;
        if (is_set == set) {
            return ASUS_EC_OK;
        }
        poll_pause();
    }
    return timeout_error;
}

static asus_ec_result drain_output_buffer(void) {
    unsigned int drained = 0;

    while ((inb(ASUS_EC_COMMAND_PORT) & OBF_BIT) != 0) {
        (void)inb(ASUS_EC_DATA_PORT);
        drained++;
        if (drained >= MAX_DRAIN_BYTES) {
            return ASUS_EC_ERR_DRAIN;
        }
        poll_pause();
    }
    return ASUS_EC_OK;
}

static asus_ec_result write_command(uint8_t value) {
    asus_ec_result result =
        wait_for_status(IBF_BIT, false, ASUS_EC_ERR_TIMEOUT_IBF);
    if (result != ASUS_EC_OK) {
        return result;
    }
    outb(value, ASUS_EC_COMMAND_PORT);
    return ASUS_EC_OK;
}

static asus_ec_result write_data(uint8_t value) {
    asus_ec_result result =
        wait_for_status(IBF_BIT, false, ASUS_EC_ERR_TIMEOUT_IBF);
    if (result != ASUS_EC_OK) {
        return result;
    }
    outb(value, ASUS_EC_DATA_PORT);
    return ASUS_EC_OK;
}

static asus_ec_result read_data(uint8_t *value) {
    asus_ec_result result =
        wait_for_status(OBF_BIT, true, ASUS_EC_ERR_TIMEOUT_OBF);
    if (result != ASUS_EC_OK) {
        return result;
    }
    *value = inb(ASUS_EC_DATA_PORT);
    return ASUS_EC_OK;
}

static asus_ec_result transaction(const uint8_t payload[3], uint8_t *reply) {
    asus_ec_result result = drain_output_buffer();
    if (result != ASUS_EC_OK) {
        return result;
    }
    result = write_command(ASUS_EC_COMMAND);
    if (result != ASUS_EC_OK) {
        return result;
    }
    for (size_t index = 0; index < 3; index++) {
        result = write_data(payload[index]);
        if (result != ASUS_EC_OK) {
            return result;
        }
    }
    if (reply != NULL) {
        return read_data(reply);
    }
    return wait_for_status(IBF_BIT, false, ASUS_EC_ERR_TIMEOUT_IBF);
}

static asus_ec_result select_fan(uint8_t fan) {
    const uint8_t payload[3] = {0x82, 0x32, fan};
    return transaction(payload, NULL);
}

static asus_ec_result validate_fan(uint8_t fan) {
    uint8_t count = 0;
    const asus_ec_result result = asus_ec_fan_count(&count);
    if (result != ASUS_EC_OK) {
        return result;
    }
    if (count == 0 || count > 8 || fan >= count) {
        return ASUS_EC_ERR_PROTOCOL;
    }
    return ASUS_EC_OK;
}

static asus_ec_result read_fan_value(uint8_t fan, uint8_t operation,
                                     uint8_t *value) {
    asus_ec_result result = validate_fan(fan);
    if (result != ASUS_EC_OK) {
        return result;
    }
    result = select_fan(fan);
    if (result != ASUS_EC_OK) {
        return result;
    }
    const uint8_t payload[3] = {0x02, operation, 0x00};
    return transaction(payload, value);
}

asus_ec_result asus_ec_open(void) {
    if (io_open) {
        return ASUS_EC_OK;
    }
    if (ioperm(ASUS_EC_DATA_PORT, 2, 1) != 0) {
        return ASUS_EC_ERR_PERMISSION;
    }
    io_open = true;
    return ASUS_EC_OK;
}

void asus_ec_close(void) {
    if (io_open) {
        (void)ioperm(ASUS_EC_DATA_PORT, 2, 0);
        io_open = false;
    }
}

asus_ec_result asus_ec_status(uint8_t *status) {
    if (!io_open || status == NULL) {
        return ASUS_EC_ERR_PROTOCOL;
    }
    *status = inb(ASUS_EC_COMMAND_PORT);
    return ASUS_EC_OK;
}

asus_ec_result asus_ec_fan_count(uint8_t *count) {
    if (!io_open || count == NULL) {
        return ASUS_EC_ERR_PROTOCOL;
    }
    const uint8_t payload[3] = {0x02, 0x30, 0x00};
    return transaction(payload, count);
}

asus_ec_result asus_ec_rpm(uint8_t fan, uint16_t *rpm) {
    uint8_t low = 0;
    uint8_t high = 0;
    if (!io_open || rpm == NULL) {
        return ASUS_EC_ERR_PROTOCOL;
    }
    asus_ec_result result = read_fan_value(fan, 0x33, &low);
    if (result != ASUS_EC_OK) {
        return result;
    }
    result = read_fan_value(fan, 0x34, &high);
    if (result != ASUS_EC_OK) {
        return result;
    }
    *rpm = ((uint16_t)high << 8) | low;
    return ASUS_EC_OK;
}

asus_ec_result asus_ec_test_mode(uint8_t fan, uint8_t *enabled) {
    uint8_t value = 0;
    if (!io_open || enabled == NULL) {
        return ASUS_EC_ERR_PROTOCOL;
    }
    const asus_ec_result result = read_fan_value(fan, 0x31, &value);
    if (result != ASUS_EC_OK) {
        return result;
    }
    *enabled = value != 0;
    return ASUS_EC_OK;
}

asus_ec_result asus_ec_set_percent(uint8_t fan, uint8_t percent) {
    if (!io_open || percent < 1 || percent > 100) {
        return ASUS_EC_ERR_PROTOCOL;
    }
    asus_ec_result result = validate_fan(fan);
    if (result != ASUS_EC_OK) {
        return result;
    }
    result = select_fan(fan);
    if (result != ASUS_EC_OK) {
        return result;
    }
    const uint8_t enable[3] = {0x82, 0x31, 0x01};
    result = transaction(enable, NULL);
    if (result != ASUS_EC_OK) {
        return result;
    }
    const uint8_t pwm = (uint8_t)(((unsigned int)percent * 255U + 50U) / 100U);
    const uint8_t set_pwm[3] = {0x82, 0x35, pwm};
    result = transaction(set_pwm, NULL);
    if (result != ASUS_EC_OK) {
        const uint8_t disable[3] = {0x82, 0x31, 0x00};
        (void)transaction(disable, NULL);
    }
    return result;
}

asus_ec_result asus_ec_restore(uint8_t fan) {
    if (!io_open) {
        return ASUS_EC_ERR_PROTOCOL;
    }
    asus_ec_result result = validate_fan(fan);
    if (result != ASUS_EC_OK) {
        return result;
    }
    result = select_fan(fan);
    if (result != ASUS_EC_OK) {
        return result;
    }
    const uint8_t disable[3] = {0x82, 0x31, 0x00};
    return transaction(disable, NULL);
}

const char *asus_ec_error_code(asus_ec_result result) {
    switch (result) {
    case ASUS_EC_ERR_PERMISSION: return "PERMISSION_DENIED";
    case ASUS_EC_ERR_TIMEOUT_IBF: return "EC_TIMEOUT_IBF";
    case ASUS_EC_ERR_TIMEOUT_OBF: return "EC_TIMEOUT_OBF";
    case ASUS_EC_ERR_DRAIN: return "EC_DRAIN_FAILED";
    case ASUS_EC_ERR_PROTOCOL: return "EC_PROTOCOL_ERROR";
    case ASUS_EC_OK: return "OK";
    }
    return "EC_UNKNOWN_ERROR";
}

const char *asus_ec_error_message(asus_ec_result result) {
    switch (result) {
    case ASUS_EC_ERR_PERMISSION:
        return "Unable to acquire access to EC I/O ports 0x25c-0x25d";
    case ASUS_EC_ERR_TIMEOUT_IBF:
        return "Timed out waiting for the EC input buffer to clear";
    case ASUS_EC_ERR_TIMEOUT_OBF:
        return "Timed out waiting for EC response data";
    case ASUS_EC_ERR_DRAIN:
        return "EC output buffer did not drain within the safety limit";
    case ASUS_EC_ERR_PROTOCOL:
        return "The EC returned an invalid value or the request was invalid";
    case ASUS_EC_OK: return "Success";
    }
    return "Unknown EC error";
}
