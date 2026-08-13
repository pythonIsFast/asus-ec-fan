#define _POSIX_C_SOURCE 200809L

#include "asus_ec_protocol.h"

#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <sys/io.h>
#include <time.h>

#define OBF_BIT 0x01
#define IBF_BIT 0x02
#define POLL_NS 100000L
#define IBF_MAX_POLLS 1000U
#define OBF_MAX_POLLS 50U
#define DRAIN_MAX_POLLS 1000U

#ifdef ASUS_EC_TESTING
extern int asus_ec_test_ioperm(unsigned long from, unsigned long count, int turn_on);
extern unsigned char asus_ec_test_inb(unsigned short port);
extern void asus_ec_test_outb(unsigned char value, unsigned short port);
#define PORT_IOPERM asus_ec_test_ioperm
#define PORT_IN asus_ec_test_inb
#define PORT_OUT asus_ec_test_outb
#else
#define PORT_IOPERM ioperm
#define PORT_IN inb
#define PORT_OUT outb
#endif

static bool io_open;

static void poll_pause(void) {
    const struct timespec delay = {.tv_sec = 0, .tv_nsec = POLL_NS};
    (void)nanosleep(&delay, NULL);
}

static asus_ec_result wait_for_status(uint8_t mask, bool set,
                                      unsigned int max_polls,
                                      asus_ec_result timeout_error) {
    for (unsigned int attempt = 0; attempt < max_polls; attempt++) {
        const bool is_set = (PORT_IN(ASUS_EC_COMMAND_PORT) & mask) != 0;
        if (is_set == set) {
            return ASUS_EC_OK;
        }
        poll_pause();
    }
    return timeout_error;
}

static asus_ec_result drain_output_buffer(void) {
    for (unsigned int attempt = 0; attempt < DRAIN_MAX_POLLS; attempt++) {
        if ((PORT_IN(ASUS_EC_COMMAND_PORT) & OBF_BIT) == 0) {
            return ASUS_EC_OK;
        }
        (void)PORT_IN(ASUS_EC_DATA_PORT);
        poll_pause();
    }
    return ASUS_EC_ERR_DRAIN;
}

static asus_ec_result write_command(uint8_t value) {
    asus_ec_result result =
        wait_for_status(IBF_BIT, false, IBF_MAX_POLLS, ASUS_EC_ERR_TIMEOUT_IBF);
    if (result != ASUS_EC_OK) {
        return result;
    }
    PORT_OUT(value, ASUS_EC_COMMAND_PORT);
    return ASUS_EC_OK;
}

static asus_ec_result write_data(uint8_t value) {
    asus_ec_result result =
        wait_for_status(IBF_BIT, false, IBF_MAX_POLLS, ASUS_EC_ERR_TIMEOUT_IBF);
    if (result != ASUS_EC_OK) {
        return result;
    }
    PORT_OUT(value, ASUS_EC_DATA_PORT);
    return ASUS_EC_OK;
}

static asus_ec_result read_data(uint8_t *value) {
    asus_ec_result result =
        wait_for_status(OBF_BIT, true, OBF_MAX_POLLS, ASUS_EC_ERR_TIMEOUT_OBF);
    if (result != ASUS_EC_OK) {
        return result;
    }
    *value = PORT_IN(ASUS_EC_DATA_PORT);
    return ASUS_EC_OK;
}

static asus_ec_result write_transaction(const uint8_t payload[3]) {
    asus_ec_result result = drain_output_buffer();
    if (result != ASUS_EC_OK) {
        return result;
    }
    result = write_command(ASUS_EC_WAKE_COMMAND);
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
    return wait_for_status(IBF_BIT, false, IBF_MAX_POLLS,
                           ASUS_EC_ERR_TIMEOUT_IBF);
}

static asus_ec_result read_transaction(const uint8_t payload[3], uint8_t *reply) {
    if (reply == NULL) {
        return ASUS_EC_ERR_PROTOCOL;
    }
    for (unsigned int attempt = 0; attempt < 2; attempt++) {
        asus_ec_result result = write_transaction(payload);
        if (result != ASUS_EC_OK) {
            return result;
        }
        result = read_data(reply);
        if (result == ASUS_EC_OK) {
            return ASUS_EC_OK;
        }
        if (result != ASUS_EC_ERR_TIMEOUT_OBF) {
            return result;
        }
    }
    return ASUS_EC_ERR_TIMEOUT_OBF;
}

static asus_ec_result select_fan(uint8_t fan) {
    const uint8_t payload[3] = {0x82, 0x32, fan};
    return write_transaction(payload);
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

static asus_ec_result read_value(uint8_t operation, uint8_t *value) {
    const uint8_t payload[3] = {0x02, operation, 0x00};
    return read_transaction(payload, value);
}

asus_ec_result asus_ec_open(void) {
    if (io_open) {
        return ASUS_EC_OK;
    }
    if (PORT_IOPERM(ASUS_EC_DATA_PORT, 2, 1) != 0) {
        return ASUS_EC_ERR_PERMISSION;
    }
    io_open = true;
    return ASUS_EC_OK;
}

void asus_ec_close(void) {
    if (io_open) {
        (void)PORT_IOPERM(ASUS_EC_DATA_PORT, 2, 0);
        io_open = false;
    }
}

asus_ec_result asus_ec_status(uint8_t *status) {
    if (!io_open || status == NULL) {
        return ASUS_EC_ERR_PROTOCOL;
    }
    *status = PORT_IN(ASUS_EC_COMMAND_PORT);
    return ASUS_EC_OK;
}

asus_ec_result asus_ec_fan_count(uint8_t *count) {
    if (!io_open || count == NULL) {
        return ASUS_EC_ERR_PROTOCOL;
    }
    const uint8_t payload[3] = {0x02, 0x30, 0x00};
    return read_transaction(payload, count);
}

asus_ec_result asus_ec_rpm(uint8_t fan, uint16_t *rpm) {
    uint8_t low = 0;
    uint8_t high = 0;
    if (!io_open || rpm == NULL) {
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
    result = read_value(0x34, &high);
    if (result != ASUS_EC_OK) {
        return result;
    }
    result = read_value(0x33, &low);
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
    asus_ec_result result = validate_fan(fan);
    if (result != ASUS_EC_OK) {
        return result;
    }
    result = select_fan(fan);
    if (result != ASUS_EC_OK) {
        return result;
    }
    result = read_value(0x31, &value);
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
    result = write_transaction(enable);
    if (result != ASUS_EC_OK) {
        return result;
    }
    const uint8_t pwm = (uint8_t)(((unsigned int)percent * 255U + 50U) / 100U);
    const uint8_t set_pwm[3] = {0x82, 0x35, pwm};
    return write_transaction(set_pwm);
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
    result = write_transaction(disable);
    if (result != ASUS_EC_OK) {
        return result;
    }
    const uint8_t zero_pwm[3] = {0x82, 0x35, 0x00};
    return write_transaction(zero_pwm);
}

const char *asus_ec_error_code(asus_ec_result result) {
    switch (result) {
    case ASUS_EC_ERR_PERMISSION: return "PERMISSION_DENIED";
    case ASUS_EC_ERR_TIMEOUT_IBF: return "EC_TIMEOUT_IBF";
    case ASUS_EC_ERR_TIMEOUT_OBF: return "EC_TIMEOUT_OBF";
    case ASUS_EC_ERR_DRAIN: return "EC_DRAIN_FAILED";
    case ASUS_EC_ERR_PROTOCOL: return "EC_PROTOCOL_ERROR";
    case ASUS_EC_ERR_VERIFY: return "EC_VERIFY_FAILED";
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
    case ASUS_EC_ERR_VERIFY:
        return "The EC did not confirm the requested fan control mode";
    case ASUS_EC_OK: return "Success";
    }
    return "Unknown EC error";
}
