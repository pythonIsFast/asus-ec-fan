CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra -Werror -pedantic -std=c11
TARGET := asus-ec-fan-helper
SOURCES := asus_ec_helper.c asus_ec_protocol.c

.PHONY: all clean

all: $(TARGET)

$(TARGET): $(SOURCES) asus_ec_protocol.h
	$(CC) $(CFLAGS) -o $@ $(SOURCES)

clean:
	$(RM) $(TARGET)
