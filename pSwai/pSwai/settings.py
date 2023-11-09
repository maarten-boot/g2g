"""
Django settings for pSwai project.
"""

import os
import sys
import environ
import ldap

from pathlib import Path
from dotenv import find_dotenv

from django_auth_ldap.config import (
    LDAPSearch,
    ActiveDirectoryGroupType,
)
from django.forms.renderers import TemplatesSetting

# ------------------------
# set up env
env = environ.Env()
env_file = find_dotenv()
if not env_file:
    print("FATAL: failed to find the '.env' file", file=sys.stderr)
    exit(101)

environ.Env.read_env(env_file=env_file)
# end setup env
# ------------------------

BASE_DIR = Path(__file__).resolve().parent.parent
ENVIRONMENT = env.str("ENVIRONMENT") # switch between prod and dev
SECRET_KEY = env.str("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = tuple(env.list("DJANGO_ALLOWED_HOSTS", default=[]))


# Application definition

INSTALLED_APPS = [
    "aGit2Git",
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
LDAP_IGNORE_CERT_ERRORS = True

AUTH_LDAP_CONNECTION_OPTIONS = {
    ldap.OPT_REFERRALS: 0,  # int
    ldap.OPT_X_TLS_REQUIRE_CERT: ldap.OPT_X_TLS_ALLOW,
    # do not enfoce a valid Cert
}

AUTH_LDAP_GLOBAL_OPTIONS = {
    ldap.OPT_X_TLS_REQUIRE_CERT: ldap.OPT_X_TLS_ALLOW,
    # do not enfoce a valid Cert
    ldap.OPT_REFERRALS: 0,  # int
}

AUTH_LDAP_BIND_DN = os.getenv("LDAP_BIND_DN")
AUTH_LDAP_BIND_PASSWORD = os.getenv("LDAP_BIND_PW")

XLDAP_BASE = os.getenv("LDAP_BASE")

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

AUTH_LDAP_USER_FLAGS_BY_GROUP = {
    "is_staff": env.str("LDAP_STAFF"),
    "is_active": env.str("LDAP_ACTIVE"),
}

AUTH_LDAP_USER_ATTR_MAP = {
    "username": "sAMAccountName",
    "first_name": "givenName",
    "last_name": "sn",
    "email": "mail",  # other fields as needed
}

# To ensure user object is updated each time on login
AUTH_LDAP_ALWAYS_UPDATE_USER = True

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

DATETIME_FORMAT = "ymd-His"
USE_L10N = False  # needed to make the line above work

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.2/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = os.path.join(BASE_DIR, "static")


# Default primary key field type
# https://docs.djangoproject.com/en/4.2/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGGING = {
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
        "file": {
            "level": env.str("DJANGO_LOG_LEVEL", default="WARNING"),
            "class": "logging.FileHandler",
            "formatter": "verbose",
            "filename": "/tmp/django.log",
        },
        "syslog": {
            "level": env.str("DJANGO_LOG_LEVEL", default="WARNING"),
            "class": "logging.handlers.SysLogHandler",
            "formatter": "verbose",
            "facility": "local7",
            "address": "/dev/log",
        },
        "mail_admins": {
            "level": env.str("DJANGO_LOG_LEVEL_MAIL", default="ERROR"),
            "class": "django.utils.log.AdminEmailHandler",
            "include_html": True,
        },
        "stream_to_console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
        },
    },
    "root": {
        "handlers": env.list(
            "DJANGO_LOGGERS_HANDLERS_ROOT",
            default=[],
        ),
        "level": env.str("DJANGO_LOG_LEVEL", default="WARNING"),
    },
    "loggers": {
        "django": {
            "handlers": env.list("DJANGO_LOGGERS_HANDLERS", default=[]),
            "level": env.str("DJANGO_LOG_LEVEL", default="WARNING"),
            "propagate": False,
        },
        "django_auth_ldap": {
            "handlers": ["stream_to_console"],
            "level": "DEBUG",
            "propagate": True,
        },
    },
}


MY_LOGGERS = {}
for app in INSTALLED_APPS:
    MY_LOGGERS[app] = {
        "handlers": env.list("DJANGO_LOGGERS_HANDLERS_APP"),
        "level": env.str("DJANGO_LOG_LEVEL", default="WARNING"),
        "propagate": True,
    }
LOGGING["loggers"].update(MY_LOGGERS)


class CustomFormRenderer(TemplatesSetting):
    form_template_name = "form_snippet.html"

FORM_RENDERER = "pSwai.settings.CustomFormRenderer"
