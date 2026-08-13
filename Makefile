PYTHON ?= python3
VENV ?= .venv
VENV_PYTHON := $(VENV)/bin/python

.PHONY: all setup helper test run mock hardware-test clean

all: helper

setup:
	$(PYTHON) -m venv $(VENV)
	$(VENV_PYTHON) -m pip install --upgrade pip
	$(VENV_PYTHON) -m pip install -r requirements-dev.txt

helper:
	$(MAKE) -C helper

test:
	$(VENV_PYTHON) -m pytest -q

run: helper
	$(VENV_PYTHON) app.py

mock:
	$(VENV_PYTHON) app.py --mock

hardware-test: helper
	@test "$$(id -u)" -eq 0 || (echo "hardware-test requires explicit root invocation"; exit 1)
	@echo "Read-only EC helper checks"
	helper/asus-ec-fan-helper status
	helper/asus-ec-fan-helper fan-count

clean:
	$(MAKE) -C helper clean
