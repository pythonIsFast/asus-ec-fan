PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python
TARGET_USER ?= $(SUDO_USER)

.PHONY: all setup helper test run mock install-helper authorize-user hardware-test clean

all: helper

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements-dev.txt

helper:
	$(MAKE) -C helper

test:
	$(MAKE) -C helper test
	$(VENV_PYTHON) -m pytest -q

run: helper
	$(VENV_PYTHON) app.py

mock:
	$(VENV_PYTHON) app.py --mock

install-helper:
	@test "$$(id -u)" -eq 0 || (echo "install-helper must be run with sudo"; exit 1)
	@test -x helper/asus-ec-fan-helper || (echo "Run 'make helper' as your normal user first"; exit 1)
	@command -v visudo >/dev/null || (echo "visudo is required to validate sudoers policy"; exit 1)
	visudo -cf packaging/asus-ec-fan.sudoers
	groupadd --system --force asus-ec-fan
	install -d -o root -g root -m 0755 /usr/local/libexec
	install -o root -g root -m 0755 helper/asus-ec-fan-helper /usr/local/libexec/asus-ec-fan-helper
	install -o root -g root -m 0440 packaging/asus-ec-fan.sudoers /etc/sudoers.d/asus-ec-fan
	@echo "Helper installed. Next run: sudo make authorize-user"

authorize-user:
	@test "$$(id -u)" -eq 0 || (echo "authorize-user must be run with sudo"; exit 1)
	@test -n "$(TARGET_USER)" && test "$(TARGET_USER)" != root || (echo "Set TARGET_USER to the desktop user"; exit 1)
	id "$(TARGET_USER)" >/dev/null
	usermod -aG asus-ec-fan "$(TARGET_USER)"
	@echo "Authorized $(TARGET_USER). Log out and back in before running the app."

hardware-test:
	@test "$$(id -u)" -eq 0 || (echo "hardware-test requires explicit root invocation"; exit 1)
	@test -x helper/asus-ec-fan-helper || (echo "Run 'make helper' as your normal user first"; exit 1)
	@echo "Read-only EC helper checks"
	helper/asus-ec-fan-helper status
	helper/asus-ec-fan-helper fan-count

clean:
	$(MAKE) -C helper clean
