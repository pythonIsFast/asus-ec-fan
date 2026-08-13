#include "asus_ec_protocol.h"

#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#define MAX_EVENTS 256

typedef struct {
    uint8_t value;
    uint16_t port;
} io_event;

static io_event events[MAX_EVENTS];
static size_t event_count;
static uint8_t payload[3];
static size_t payload_size;
static bool response_pending;
static uint8_t response;
static bool test_mode;
static bool force_ibf;
static bool drop_next_response;
static unsigned int ioperm_on_calls;
static unsigned int ioperm_off_calls;

static void reset_mock(void) {
    memset(events, 0, sizeof(events));
    event_count = 0;
    memset(payload, 0, sizeof(payload));
    payload_size = 0;
    response_pending = false;
    response = 0;
    test_mode = false;
    force_ibf = false;
    drop_next_response = false;
    ioperm_on_calls = 0;
    ioperm_off_calls = 0;
}

int asus_ec_test_ioperm(unsigned long from, unsigned long count, int turn_on) {
    assert(from == ASUS_EC_DATA_PORT);
    assert(count == 2);
    if (turn_on) {
        ioperm_on_calls++;
    } else {
        ioperm_off_calls++;
    }
    return 0;
}

unsigned char asus_ec_test_inb(unsigned short port) {
    if (port == ASUS_EC_COMMAND_PORT) {
        if (force_ibf) {
            return 0x02;
        }
        return response_pending ? 0x01 : 0x00;
    }
    assert(port == ASUS_EC_DATA_PORT);
    assert(response_pending);
    response_pending = false;
    return response;
}

static void finish_payload(void) {
    if (payload[0] == 0x02) {
        if (drop_next_response) {
            drop_next_response = false;
            return;
        }
        switch (payload[1]) {
        case 0x30: response = 1; break;
        case 0x31: response = test_mode ? 1 : 0; break;
        case 0x34: response = 0x0f; break;
        case 0x33: response = 0x0a; break;
        default: assert(!"unexpected read register");
        }
        response_pending = true;
    } else if (payload[0] == 0x82 && payload[1] == 0x31) {
        test_mode = payload[2] != 0;
    }
}

void asus_ec_test_outb(unsigned char value, unsigned short port) {
    assert(event_count < MAX_EVENTS);
    events[event_count++] = (io_event){.value = value, .port = port};
    if (port == ASUS_EC_COMMAND_PORT) {
        if (value == ASUS_EC_COMMAND) {
            payload_size = 0;
        }
        return;
    }
    assert(port == ASUS_EC_DATA_PORT);
    assert(payload_size < sizeof(payload));
    payload[payload_size++] = value;
    if (payload_size == sizeof(payload)) {
        finish_payload();
    }
}

static void assert_transaction(size_t offset, uint8_t first, uint8_t second,
                               uint8_t third) {
    assert(offset + 4 < event_count);
    assert(events[offset].port == ASUS_EC_COMMAND_PORT);
    assert(events[offset].value == ASUS_EC_WAKE_COMMAND);
    assert(events[offset + 1].port == ASUS_EC_COMMAND_PORT);
    assert(events[offset + 1].value == ASUS_EC_COMMAND);
    assert(events[offset + 2].port == ASUS_EC_DATA_PORT);
    assert(events[offset + 2].value == first);
    assert(events[offset + 3].value == second);
    assert(events[offset + 4].value == third);
}

static void open_mock(void) {
    assert(asus_ec_open() == ASUS_EC_OK);
    assert(ioperm_on_calls == 1);
}

static void close_mock(void) {
    asus_ec_close();
    assert(ioperm_off_calls == 1);
}

static void test_manual_sequence(void) {
    reset_mock();
    open_mock();
    assert(asus_ec_set_percent(0, 60) == ASUS_EC_OK);
    assert(event_count == 20);
    assert_transaction(0, 0x02, 0x30, 0x00);
    assert_transaction(5, 0x82, 0x32, 0x00);
    assert_transaction(10, 0x82, 0x31, 0x01);
    assert_transaction(15, 0x82, 0x35, 0x99);
    assert(test_mode);
    close_mock();
}

static void test_restore_sequence(void) {
    reset_mock();
    test_mode = true;
    open_mock();
    assert(asus_ec_restore(0) == ASUS_EC_OK);
    assert(event_count == 20);
    assert_transaction(0, 0x02, 0x30, 0x00);
    assert_transaction(5, 0x82, 0x32, 0x00);
    assert_transaction(10, 0x82, 0x31, 0x00);
    assert_transaction(15, 0x82, 0x35, 0x00);
    assert(!test_mode);
    close_mock();
}

static void test_rpm_order_and_value(void) {
    reset_mock();
    open_mock();
    uint16_t rpm = 0;
    assert(asus_ec_rpm(0, &rpm) == ASUS_EC_OK);
    assert(rpm == 3850);
    assert_transaction(10, 0x02, 0x34, 0x00);
    assert_transaction(15, 0x02, 0x33, 0x00);
    close_mock();
}

static void test_read_retries_once(void) {
    reset_mock();
    drop_next_response = true;
    open_mock();
    uint8_t count = 0;
    assert(asus_ec_fan_count(&count) == ASUS_EC_OK);
    assert(count == 1);
    assert(event_count == 10);
    assert_transaction(0, 0x02, 0x30, 0x00);
    assert_transaction(5, 0x02, 0x30, 0x00);
    close_mock();
}

static void test_ibf_timeout(void) {
    reset_mock();
    force_ibf = true;
    open_mock();
    uint8_t count = 0;
    assert(asus_ec_fan_count(&count) == ASUS_EC_ERR_TIMEOUT_IBF);
    assert(event_count == 0);
    close_mock();
}

int main(void) {
    test_manual_sequence();
    test_restore_sequence();
    test_rpm_order_and_value();
    test_read_retries_once();
    test_ibf_timeout();
    puts("C protocol tests passed");
    return 0;
}
