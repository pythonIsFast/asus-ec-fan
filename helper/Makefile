CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -Werror -pedantic -std=c11
TARGET := asus-ec-fan-helper
SOURCES := asus_ec_helper.c asus_ec_protocol.c
TEST_TARGET := test-asus-ec-protocol

.PHONY: all test clean

all: $(TARGET)

$(TARGET): $(SOURCES) asus_ec_protocol.h
	$(CC) $(CFLAGS) -o $@ $(SOURCES)

$(TEST_TARGET): test_asus_ec_protocol.c asus_ec_protocol.c asus_ec_protocol.h
	$(CC) $(CFLAGS) -DASUS_EC_TESTING -o $@ test_asus_ec_protocol.c asus_ec_protocol.c

test: $(TEST_TARGET)
	./$(TEST_TARGET)

clean:
	$(RM) $(TARGET) $(TEST_TARGET)
