#ifndef ASUS_EC_PROTOCOL_H
#define ASUS_EC_PROTOCOL_H

#include <stdint.h>

#define ASUS_EC_DATA_PORT 0x25c
#define ASUS_EC_COMMAND_PORT 0x25d
#define ASUS_EC_COMMAND 0xdd

typedef enum {
    ASUS_EC_OK = 0,
    ASUS_EC_ERR_PERMISSION,
    ASUS_EC_ERR_TIMEOUT_IBF,
    ASUS_EC_ERR_TIMEOUT_OBF,
    ASUS_EC_ERR_DRAIN,
    ASUS_EC_ERR_PROTOCOL
} asus_ec_result;

asus_ec_result asus_ec_open(void);
void asus_ec_close(void);
asus_ec_result asus_ec_status(uint8_t *status);
asus_ec_result asus_ec_fan_count(uint8_t *count);
asus_ec_result asus_ec_rpm(uint8_t fan, uint16_t *rpm);
asus_ec_result asus_ec_test_mode(uint8_t fan, uint8_t *enabled);
asus_ec_result asus_ec_set_percent(uint8_t fan, uint8_t percent);
asus_ec_result asus_ec_restore(uint8_t fan);
const char *asus_ec_error_code(asus_ec_result result);
const char *asus_ec_error_message(asus_ec_result result);

#endif
