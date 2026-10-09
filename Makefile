# Makefile: ts=4
SHELL = /usr/bin/bash
export SHELL

VENV 	:= venv
export VENV

# -----------------------
NAME= gunicorn003
SERVICE = $(NAME).service
SOCKET = $(NAME).socket

# -----------------------
CODE := pSwai

PYTHON = python3.14
PIP := venv/bin/pip3 -q --disable-pip-version-check --no-color --require-virtualenv --no-cache-dir
PY = $(VENV)/bin/python3

PYTHON_PREP_VENV := \
	$(PYTHON) -m venv venv; \
	$(PYTHON) -m venv --upgrade venv; \
	source $(VENV)/bin/activate; \
	$(PIP) install -U -r requirements.txt

.PHONY: prep clean restart mypy ruff

all: clean venv prep

clean:
	rm -rf $(VENV)

prep: ruff mypy

$(VENV):
	$(PYTHON_PREP_VENV)

ruff: $(VENV)
	$(PIP) install ruff; \
	ruff format $(CODE); \
	ruff check --fix $(CODE) || exit 0 # dont fail

mypy: $(VENV)
	$(PIP) install mypy; \
	mypy \
		--ignore-missing-imports \
		--no-incremental \
		$(CODE) || exit 0

restart:
	[ -f /etc/systemd/system/gunicorn003.service ] && sudo systemctl restart gunicorn003
