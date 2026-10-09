# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# builder: python-ldap has no wheels, it must be compiled against libldap
# ---------------------------------------------------------------------------
FROM python:3.14-slim-bookworm AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libldap2-dev \
        libsasl2-dev \
        libssl-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements.txt /tmp/requirements.txt
RUN pip install --upgrade pip \
    && pip install -r /tmp/requirements.txt

# ---------------------------------------------------------------------------
# runtime: shared libraries only, no compilers in the shipped image
# ---------------------------------------------------------------------------
FROM python:3.14-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE=pSwai.settings

# ca-certificates provides /etc/ssl/certs/ca-certificates.crt; compose mounts the host's bundle
# over it so the internal CAs (LDAP_CA_CERT_FILE) are trusted inside the container too
RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        libldap-2.5-0 \
        libsasl2-2 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

RUN useradd --create-home --uid 10001 app
WORKDIR /app

# the django project root is pSwai/ inside the repo, so manage.py lands at /app/manage.py
COPY --chown=app:app pSwai/ /app/
COPY --chown=app:app docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# STATIC_ROOT is BASE_DIR/static; /var/tmp/django is the FileBasedCache LOCATION
RUN mkdir -p /app/static /var/tmp/django \
    && chown -R app:app /app/static /var/tmp/django

USER app
EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["gunicorn", "pSwai.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
