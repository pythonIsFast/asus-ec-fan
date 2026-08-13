#include "asus_ec_protocol.h"

#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define DMI_PRODUCT_NAME "/sys/class/dmi/id/product_name"

static int fail(asus_ec_result result) {
    printf("{\"ok\":false,\"error\":\"%s\",\"message\":\"%s\"}\n",
           asus_ec_error_code(result), asus_ec_error_message(result));
    return 1;
}

static int usage(void) {
    printf("{\"ok\":false,\"error\":\"INVALID_ARGUMENT\","
           "\"message\":\"Expected status, fan-count, rpm <fan>, "
           "test-mode <fan>, set <fan> <percent>, or restore <fan>\"}\n");
    return 2;
}

static int unsupported(void) {
    printf("{\"ok\":false,\"error\":\"UNSUPPORTED_HARDWARE\","
           "\"message\":\"Fan writes are allowed only on ASUS BR1402FGA\"}\n");
    return 1;
}

static int supported_model(void) {
    char model[128] = {0};
    FILE *file = fopen(DMI_PRODUCT_NAME, "r");
    if (file == NULL) {
        return 0;
    }
    const int read_ok = fgets(model, sizeof(model), file) != NULL;
    (void)fclose(file);
    if (!read_ok) {
        return 0;
    }
    model[strcspn(model, "\r\n")] = '\0';
    return strcmp(model, "ASUS BR1402FGA") == 0 ||
           strcmp(model, "BR1402FGA") == 0;
}

static int parse_number(const char *text, unsigned long maximum,
                        unsigned long *value) {
    char *end = NULL;
    errno = 0;
    const unsigned long parsed = strtoul(text, &end, 10);
    if (errno != 0 || text[0] == '\0' || end == NULL || *end != '\0' ||
        parsed > maximum) {
        return -1;
    }
    *value = parsed;
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        return usage();
    }
    if ((strcmp(argv[1], "set") == 0 || strcmp(argv[1], "restore") == 0) &&
        !supported_model()) {
        return unsupported();
    }
    const asus_ec_result open_result = asus_ec_open();
    if (open_result != ASUS_EC_OK) {
        return fail(open_result);
    }

    int exit_code = 0;
    asus_ec_result result = ASUS_EC_OK;
    unsigned long fan = 0;

    if (strcmp(argv[1], "status") == 0 && argc == 2) {
        uint8_t status = 0;
        result = asus_ec_status(&status);
        if (result == ASUS_EC_OK) {
            printf("{\"ok\":true,\"status\":%u,\"obf\":%s,\"ibf\":%s}\n",
                   status, (status & 1) ? "true" : "false",
                   (status & 2) ? "true" : "false");
        }
    } else if (strcmp(argv[1], "fan-count") == 0 && argc == 2) {
        uint8_t count = 0;
        result = asus_ec_fan_count(&count);
        if (result == ASUS_EC_OK && (count == 0 || count > 8)) {
            result = ASUS_EC_ERR_PROTOCOL;
        }
        if (result == ASUS_EC_OK) {
            printf("{\"ok\":true,\"fan_count\":%u}\n", count);
        }
    } else if (strcmp(argv[1], "rpm") == 0 && argc == 3 &&
               parse_number(argv[2], 7, &fan) == 0) {
        uint16_t rpm = 0;
        result = asus_ec_rpm((uint8_t)fan, &rpm);
        if (result == ASUS_EC_OK) {
            printf("{\"ok\":true,\"fan\":%lu,\"rpm\":%u}\n", fan, rpm);
        }
    } else if (strcmp(argv[1], "test-mode") == 0 && argc == 3 &&
               parse_number(argv[2], 7, &fan) == 0) {
        uint8_t enabled = 0;
        result = asus_ec_test_mode((uint8_t)fan, &enabled);
        if (result == ASUS_EC_OK) {
            printf("{\"ok\":true,\"fan\":%lu,\"test_mode\":%s}\n",
                   fan, enabled ? "true" : "false");
        }
    } else if (strcmp(argv[1], "set") == 0 && argc == 4 &&
               parse_number(argv[2], 7, &fan) == 0) {
        unsigned long percent = 0;
        if (parse_number(argv[3], 100, &percent) != 0 || percent < 1) {
            asus_ec_close();
            return usage();
        }
        result = asus_ec_set_percent((uint8_t)fan, (uint8_t)percent);
        if (result == ASUS_EC_OK) {
            printf("{\"ok\":true,\"fan\":%lu,\"mode\":\"manual\","
                   "\"percent\":%lu}\n", fan, percent);
        }
    } else if (strcmp(argv[1], "restore") == 0 && argc == 3 &&
               parse_number(argv[2], 7, &fan) == 0) {
        result = asus_ec_restore((uint8_t)fan);
        if (result == ASUS_EC_OK) {
            printf("{\"ok\":true,\"fan\":%lu,\"mode\":\"firmware\"}\n",
                   fan);
        }
    } else {
        asus_ec_close();
        return usage();
    }

    if (result != ASUS_EC_OK) {
        exit_code = fail(result);
    }
    asus_ec_close();
    return exit_code;
}
