"""
Django settings for pSwai project.
"""

import os
import sys
from pathlib import Path

import environ
import ldap
from django.forms.renderers import TemplatesSetting
from django_auth_ldap.config import (
    ActiveDirectoryGroupType,
    LDAPGroupQuery,
    LDAPSearch,
)
from dotenv import find_dotenv

# ------------------------
# set up env
env = environ.Env()
# a local .env is optional: in docker the values come from the environment (compose env_file).
# values already in the environment win over the .env file.
env_file = find_dotenv()
if env_file:
    environ.Env.read_env(env_file=env_file)
# end setup env
# ------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = env.str("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = tuple(env.list("DJANGO_ALLOWED_HOSTS", default=[]))

# ------------------------
# security
# full origin incl. scheme and port as the browser sees it, e.g. http://g2g.example.com:8080
CSRF_TRUSTED_ORIGINS = env.list("DJANGO_CSRF_TRUSTED_ORIGINS", default=[])

SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = True  # log in again after closing the browser
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"

# set DJANGO_HTTPS=True once the site is served over https (tls terminated in the proxy)
DJANGO_HTTPS = env.bool("DJANGO_HTTPS", default=False)
if DJANGO_HTTPS:
    # nginx sets X-Forwarded-Proto; only trust it because django is never reached directly
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
    SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=0)
# end security
# ------------------------


# Application definition

INSTALLED_APPS = [
    "aGit2Git",
    "aComponents",
    "appAutoGui",
    "appLogin",
    "django.forms",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]


TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            os.path.join(BASE_DIR, "templates"),
        ],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
        "LOCATION": "/var/tmp/django",
    }
}


ROOT_URLCONF = "pSwai.urls"
WSGI_APPLICATION = "pSwai.wsgi.application"


# Database
# https://docs.djangoproject.com/en/4.2/ref/settings/#databases
DATABASES = {
    "default": env.db_url(
        "DJANGO_DATABASE_URL",
        engine="django.db.backends.postgresql_psycopg2",
    ),
}

# <<<<<<<<<<<<<<< LDAP START >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# <<<<<<<<<<<<<<< LDAP START >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

AUTH_LDAP_SERVER_URI = ",".join(
    [
        env.str("LDAP_URL1"),
        env.str("LDAP_URL2"),
    ]
)
AUTH_LDAP_START_TLS = True

# verify the LDAP server certificate, otherwise user passwords can be intercepted.
# LDAP_CA_CERT_FILE: the (internal) CA bundle that signed the AD certificates;
#   if unset the system trust store is used.
# LDAP_TLS_VERIFY=False only for local testing against a server with a broken cert.
LDAP_TLS_VERIFY = env.bool("LDAP_TLS_VERIFY", default=True)
LDAP_CA_CERT_FILE = env.str("LDAP_CA_CERT_FILE", default="")

AUTH_LDAP_CONNECTION_OPTIONS = {
    ldap.OPT_REFERRALS: 0,  # int
}

# TLS options are global: they are read when the TLS context is created on connect
AUTH_LDAP_GLOBAL_OPTIONS = {
    ldap.OPT_X_TLS_REQUIRE_CERT: ldap.OPT_X_TLS_DEMAND if LDAP_TLS_VERIFY else ldap.OPT_X_TLS_ALLOW,
    ldap.OPT_REFERRALS: 0,  # int
}
if LDAP_CA_CERT_FILE:
    AUTH_LDAP_GLOBAL_OPTIONS[ldap.OPT_X_TLS_CACERTFILE] = LDAP_CA_CERT_FILE

AUTH_LDAP_BIND_DN = os.getenv("LDAP_BIND_DN")
AUTH_LDAP_BIND_PASSWORD = os.getenv("LDAP_BIND_PW")

AUTH_LDAP_USER_SEARCH = LDAPSearch(
    os.getenv("LDAP_BASE"),
    ldap.SCOPE_SUBTREE,
    "(&(objectClass=user)(sAMAccountName=%(user)s))",
)

# Set up the basic group parameters.
AUTH_LDAP_GROUP_SEARCH = LDAPSearch(
    os.getenv("LDAP_BASE"),
    ldap.SCOPE_SUBTREE,
    "(objectClass=group)",
)

AUTH_LDAP_GROUP_TYPE = ActiveDirectoryGroupType()

# rights: every active user may view; members of LDAP_ADMIN (optional) are superusers with all rights;
# other users get add/change/delete rights through django groups (local groups, managed in the admin,
# or a django group named exactly like an AD group: AUTH_LDAP_FIND_GROUP_PERMS)
LDAP_ADMIN = env.str("LDAP_ADMIN", default="")
AUTH_LDAP_USER_FLAGS_BY_GROUP = {
    "is_active": env.str("LDAP_ACTIVE"),
    "is_staff": env.str("LDAP_STAFF"),
}
if LDAP_ADMIN:
    # admins also get the admin site, where they manage the local groups
    AUTH_LDAP_USER_FLAGS_BY_GROUP["is_staff"] = LDAPGroupQuery(env.str("LDAP_STAFF")) | LDAPGroupQuery(LDAP_ADMIN)
    AUTH_LDAP_USER_FLAGS_BY_GROUP["is_superuser"] = LDAP_ADMIN

AUTH_LDAP_USER_ATTR_MAP = {
    "username": "sAMAccountName",
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",  # other fields as needed
}

# To ensure user object is updated each time on login
AUTH_LDAP_ALWAYS_UPDATE_USER = True
AUTH_LDAP_FIND_GROUP_PERMS = True
AUTH_LDAP_CACHE_GROUPS = True
AUTH_LDAP_CACHE_TIMEOUT = 60 * 20  # 20 minutes
# not mirrored: mirroring would reset a user's django groups to exactly the AD groups at every login,
# and remove them from the local groups
AUTH_LDAP_MIRROR_GROUPS = False

AUTHENTICATION_BACKENDS = [
    # django_auth_ldap, also accepting DOMAIN\user, the UPN and the mail address as login name
    "appLogin.backends.LDAPBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# <<<<<<<<<<<<<<< LDAP END >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
# <<<<<<<<<<<<<<< LDAP END >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>

# Password validation
# https://docs.djangoproject.com/en/4.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
# https://docs.djangoproject.com/en/4.2/topics/i18n/

LANGUAGE_CODE = env.str("DJANGO_LANGUAGE_CODE", default="en-us")
TIME_ZONE = env.str("DJANGO_TIME_ZONE", default="UTC")
USE_I18N = env.bool("DJANGO_USE_I18N", default=True)
USE_TZ = env.bool("DJANGO_USE_TZ", default=True)

# date/time display formats per language: pSwai/formats/<lang>/formats.py (en: "ymd-His", e.g. 261010-093015).
# A plain DATETIME_FORMAT setting is ignored while USE_I18N is on, the locale formats win.
FORMAT_MODULE_PATH = ["pSwai.formats"]

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "static/"
# STATIC_ROOT is generated by collectstatic (not in git); our own static files live in assets/
STATIC_ROOT = os.path.join(BASE_DIR, "static")
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "assets"),
]


# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(levelname)s - [%(asctime)s] - %(name)s.%(funcName)s:%(lineno)s - %(message)s",
        }
    },
    "handlers": {
        "console": {
            "level": env.str("DJANGO_LOG_LEVEL", default="WARNING"),
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
        "syslog": {
            "level": env.str("DJANGO_LOG_LEVEL", default="WARNING"),
            "class": "logging.handlers.SysLogHandler",
            "formatter": "verbose",
            "facility": "local7",
            "address": "/dev/log",
        },
        "stream_to_console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": [],  # set below from DJANGO_LOGGERS_HANDLERS_ROOT
        "level": env.str("DJANGO_LOG_LEVEL", default="WARNING"),
    },
    "loggers": {
        "django": {
            "handlers": [],  # set below from DJANGO_LOGGERS_HANDLERS
            "level": env.str("DJANGO_LOG_LEVEL", default="WARNING"),
            "propagate": False,
        },
        "django_auth_ldap": {
            # DEBUG logs LDAP search details: only enable that while troubleshooting
            "handlers": ["stream_to_console"],
            "level": env.str("LDAP_LOG_LEVEL", default="WARNING"),
            "propagate": False,
        },
    },
}


def _log_handlers(var: str, default: list[str] | None = None) -> list[str]:
    """the handler names in an env var, without names that are not defined above (e.g. "mail_admins"
    or "file" from an older .env): logging would refuse to start on those"""
    names = env.list(var) if default is None else env.list(var, default=default)
    unknown = [n for n in names if n not in LOGGING["handlers"]]
    if unknown:
        print(f"settings: {var}: ignoring unknown log handlers {unknown}", file=sys.stderr)
    return [n for n in names if n in LOGGING["handlers"]]


LOGGING["root"]["handlers"] = _log_handlers("DJANGO_LOGGERS_HANDLERS_ROOT", default=[])
LOGGING["loggers"]["django"]["handlers"] = _log_handlers("DJANGO_LOGGERS_HANDLERS", default=[])

# a logger per project app; the django.* apps log through the "django" logger above
_app_handlers = _log_handlers("DJANGO_LOGGERS_HANDLERS_APP")
MY_LOGGERS: dict = {}
for app in INSTALLED_APPS:
    if app.startswith("django."):
        continue
    MY_LOGGERS[str(app)] = {
        "handlers": list(_app_handlers),
        "level": env.str("DJANGO_LOG_LEVEL", default="WARNING"),
        "propagate": False,  # has its own handlers; via root every line would be logged twice
    }
for _k, _v in MY_LOGGERS.items():
    LOGGING["loggers"][_k] = _v


class CustomFormRenderer(TemplatesSetting):
    form_template_name = "form_snippet.html"


FORM_RENDERER = "pSwai.settings.CustomFormRenderer"

LOGIN_URL = "login"
