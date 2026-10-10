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
PIP := $(VENV)/bin/pip3 -q --disable-pip-version-check --no-color --require-virtualenv --no-cache-dir
PY = $(VENV)/bin/python3
RUFF = $(VENV)/bin/ruff
MYPY = $(VENV)/bin/mypy

# the image the Dockerfile builds on; requirements.txt is resolved in it
PY_IMAGE = python:3.14-slim-bookworm

.PHONY: all prep clean restart mypy ruff check test requirements docker_test

all: clean venv prep

clean:
	rm -rf $(VENV)
	rm -rf .mypy_cache
	rm -rf .ruff_cache

prep: ruff mypy

# python-ldap needs libldap2-dev and libsasl2-dev to build
$(VENV): requirements.txt requirements-dev.txt
	$(PYTHON) -m venv $(VENV)
	$(PIP) install -U -r requirements-dev.txt
	touch $(VENV)

# format and autofix; reports but does not fail
ruff: $(VENV)
	$(RUFF) format $(CODE)
	$(RUFF) check --fix $(CODE) || exit 0 # dont fail

mypy: $(VENV)
	$(MYPY) --ignore-missing-imports --no-incremental $(CODE) || exit 0

# the same checks, failing on any problem (for CI / before a commit)
check: $(VENV)
	$(RUFF) format --check $(CODE)
	$(RUFF) check $(CODE)
	$(MYPY) --ignore-missing-imports --no-incremental $(CODE)

# run the django tests in the web container against the compose postgres, using the local source
test:
	docker compose run --rm -T -e RUN_MIGRATIONS=0 -e RUN_COLLECTSTATIC=0 -v ./$(CODE):/app web \
		python manage.py test --noinput

# re-pin requirements.txt from requirements.in, resolved in the same python image as the Dockerfile
requirements: requirements.in
	docker run --rm -v ./requirements.in:/requirements.in:ro $(PY_IMAGE) sh -c '\
		apt-get update -qq >/dev/null && \
		apt-get install -y -qq --no-install-recommends build-essential libldap2-dev libsasl2-dev >/dev/null 2>&1 && \
		python -m venv /v && /v/bin/pip install -q --disable-pip-version-check -r /requirements.in && \
		echo "# pinned, generated from requirements.in by \`make requirements\` ($(PY_IMAGE))" && \
		/v/bin/pip freeze' > requirements.txt.new
	mv requirements.txt.new requirements.txt

restart:
	[ -f /etc/systemd/system/gunicorn003.service ] && sudo systemctl restart gunicorn003

# fresh docker stack: copy the one real .env (pSwai/.env) next to compose.yaml, drop the volumes
# (the database is restored again from docker/dump) and rebuild the web image
docker_test:
	cp pSwai/.env .
	docker compose down -v
	docker compose up -d --build
