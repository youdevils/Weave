import os
from datetime import timedelta
from pathlib import Path

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Required — always read from env
SECRET_KEY = os.getenv("SECRET_KEY")

if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY is not set")

# DEBUG toggles automatically from env
DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"

# ALLOWED_HOSTS from env, default to local dev
ALLOWED_HOSTS = os.getenv("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# Custom email based user model
AUTH_USER_MODEL = "account.CustomUser"

# Anonymous users hitting a @login_required view are sent to the public log-in page.
LOGIN_URL = "account:login"

# Where a successful login lands when there's no "next" parameter.
LOGIN_REDIRECT_URL = "workspace:index"

# Outbound account email (verification, password reset) via Resend.
RESEND_API_KEY = os.getenv("RESEND_API_KEY")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "OnyxJar <onboarding@resend.dev>")

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Django Apps
    "account",
    "model",
    "ai",
    "assisted",
    "api",
    "ingestion",
    "publication",
    "viewer",
    "website",
    "workspace",
    # Third Party
    "rest_framework",
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

if DEBUG:
    MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

ROOT_URLCONF = "onyxjar.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "website.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "onyxjar.wsgi.application"

SESSION_COOKIE_AGE = 3600  # 1 Hour
SESSION_SAVE_EVERY_REQUEST = True

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DATABASE_NAME"),
        "USER": os.getenv("DATABASE_USER"),
        "PASSWORD": os.getenv("DATABASE_PASSWORD"),
        "HOST": os.getenv("DATABASE_HOST"),
        "PORT": os.getenv("DATABASE_PORT"),
    }
}
DATABASES["default"]["CONN_MAX_AGE"] = 60

# ------------------------------------------------------------------------------------
# MEDIA FILES
# ------------------------------------------------------------------------------------

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# File upload limits (100MB)
DATA_UPLOAD_MAX_MEMORY_SIZE = 105 * 1024 * 1024  # 105MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 105 * 1024 * 1024  # 105MB

# ------------------------------------------------------------------------------------
# STATIC FILES
# ------------------------------------------------------------------------------------

PUBLISHED_ROOT = BASE_DIR / "published"

STATIC_URL = "/static/"

# Source static files used by Django in all environments
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

# collectstatic destination
STATIC_ROOT = BASE_DIR / "staticfiles"

# ------------------------------------------------------------------------------------
# SECURITY (Enabled automatically when DEBUG=False)
# ------------------------------------------------------------------------------------

if not DEBUG:
    CSRF_COOKIE_SECURE = True
    SESSION_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.getenv("SECURE_SSL_REDIRECT", "true").lower() == "true"
    SECURE_HSTS_SECONDS = 0
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    CSRF_TRUSTED_ORIGINS = [
        "https://onyxjar.com",
        "https://www.onyxjar.com",
    ]

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# ------------------------------------------------------------------------------------
# INTERNATIONALIZATION
# ------------------------------------------------------------------------------------

from django.utils.translation import gettext_lazy as _

LANGUAGE_CODE = "en-nz"
TIME_ZONE = "Pacific/Auckland"
USE_I18N = True
USE_TZ = True

LANGUAGES = [
    ("en", _("English")),
]

LOCALE_PATHS = [
    BASE_DIR / "locale",
]


# ------------------------------------------------------------------------------------
# CELERY
# ------------------------------------------------------------------------------------

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Pacific/Auckland"

# ------------------------------------------------------------------------------------
# PROPOSAL SUBMISSION PIPELINE
# ------------------------------------------------------------------------------------

# How long a proposal may sit in PROCESSING before it's treated as
# orphaned (its worker died) and reclaimed by the next queue check.
PROPOSAL_PROCESSING_STUCK_THRESHOLD = timedelta(minutes=15)

# Hard cap on how many proposals a single user may have "live"
# (WORKING/FAILED/QUEUED/PROCESSING, or COMPLETED-but-unacknowledged)
# against one Model at a time.
PROPOSAL_MAX_LIVE_PER_MODEL = 5

# ------------------------------------------------------------------------------------
# DATA IMPORT (ingestion app)
# ------------------------------------------------------------------------------------

# Read through ingestion.services.limits at call time, so they can be tuned
# (or overridden in tests) without touching the import code.
IMPORT_MAX_FILE_BYTES = 5 * 1024 * 1024
IMPORT_MAX_ROWS = 2000  # data rows, excluding the header
IMPORT_MAX_COLUMNS = 100
IMPORT_MAX_HEADER_CHARS = 200
IMPORT_MAX_CELL_CHARS = 10_000
# ProposalChanges one import may produce (an UPDATE is one change per field).
# Sized by the Proposal Review page, which renders every change of a proposal on
# one page at roughly 13 KB of HTML each (about 13 MB at 1,000, ~60 MB at 5,000).
# Raise it only together with paginating that page.
IMPORT_MAX_CHANGES = 1000
# Zip-bomb guards for XLSX.
IMPORT_XLSX_MAX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024
IMPORT_XLSX_MAX_COMPRESSION_RATIO = 200
# A staged (uploaded, never imported) source is swept after this long.
IMPORT_STAGED_SOURCE_TTL = timedelta(hours=24)
# Problems listed in a preview (the total is always reported).
IMPORT_PROBLEMS_SHOWN = 100

# ------------------------------------------------------------------------------------
# PUBLIC WEBSITE (website app)
# ------------------------------------------------------------------------------------

# Shown in the footer copyright line and the legal pages. Set the real legal
# entity name (and a contact address) per environment.
WEBSITE_LEGAL_ENTITY = os.getenv("WEBSITE_LEGAL_ENTITY", "OnyxJar")
WEBSITE_CONTACT_EMAIL = os.getenv("WEBSITE_CONTACT_EMAIL", "")

# Where contact-form submissions are sent (Resend -> Cloudflare Email Routing).
WEBSITE_CONTACT_FORM_RECIPIENT = os.getenv(
    "WEBSITE_CONTACT_FORM_RECIPIENT", "support@onyxjar.com"
)

# ------------------------------------------------------------------------------------
# AI SERVICE LAYER (ai app)
# ------------------------------------------------------------------------------------

AI_DEFAULT_OPENAI_MODEL = os.getenv("AI_DEFAULT_OPENAI_MODEL", "gpt-4.1")

# Bounded refinement: a compiled Change Plan that still fails validation is
# retried with the issues fed back as context, up to this many times before
# the operation is marked UNRESOLVED.
AI_MAX_REFINEMENT_CYCLES = 3

# Bounded context expansion: growing the context packet when the AI names a
# specific missing reference, before giving up on that avenue.
AI_MAX_CONTEXT_EXPANSIONS = 3

# Deterministic context sizing (mirrors ExplorerQuery's DEFAULT_LIMIT=300 /
# MAX_LIMIT=1000 as a scale reference).
AI_CONTEXT_MAX_OBJECTS = 300
AI_CONTEXT_MAX_HOPS = 2

# Byte ceiling on the serialised ContextPacket (canonical_json length).
AI_CONTEXT_MAX_BYTES = 100_000

# ProposalChanges one AI operation's compiled plan may produce (same order of
# magnitude as IMPORT_MAX_CHANGES=1000; AI plans are expected far smaller).
AI_MAX_CHANGE_PLAN_ACTIONS = 100

# User-supplied intent text length.
AI_MAX_INTENT_CHARS = 4000

AI_PROVIDER_TIMEOUT_SECONDS = 60
AI_MAX_PROVIDER_RETRIES = 2

# Policy switch for the explain()-only call made when an operation reaches
# AI_MAX_REFINEMENT_CYCLES without a valid result.
AI_FINAL_EXPLANATION_ENABLED = True

# ------------------------------------------------------------------------------------
# ASSISTED TASKS (assisted app)
# ------------------------------------------------------------------------------------

# How long a QUEUED AssistedTask may sit without reaching RUNNING before it's
# treated as a silently-failed-to-enqueue dispatch and lazily reclaimed the
# next time anything checks for an active task against its Model.
ASSISTED_TASK_QUEUED_STUCK_THRESHOLD = timedelta(minutes=5)

# How long a RUNNING AssistedTask may run before it's treated as orphaned
# (its worker died) and lazily reclaimed the same way.
ASSISTED_TASK_RUNNING_STUCK_THRESHOLD = timedelta(minutes=15)

# Evidence files a user may attach when starting Assisted Create. Extracted
# text (assisted.services.evidence_extraction.extract_text) is capped per
# file by ASSISTED_MAX_EVIDENCE_EXTRACTED_CHARS before being handed to the AI
# as an asset -- AI_CONTEXT_MAX_BYTES bounds the rest of the context packet
# and never touches evidence content.
ASSISTED_MAX_EVIDENCE_FILES = 5
ASSISTED_MAX_EVIDENCE_FILE_BYTES = 1_000_000  # 1 MB per file
ASSISTED_MAX_EVIDENCE_TOTAL_BYTES = 5_000_000  # 5 MB total
ASSISTED_MAX_EVIDENCE_EXTRACTED_CHARS = 20_000  # ~5k tokens per file, heuristic

# ------------------------------------------------------------------------------------
# PLAN ENTITLEMENTS (account app)
# ------------------------------------------------------------------------------------

# Collaborator plan's monthly Assisted token allowance. None = unlimited.
# Value intentionally undecided this iteration -- the architecture supports a
# real number later with no further migration; see account.services.entitlement.
ASSISTED_TOKEN_LIMIT_COLLABORATOR = None

# ------------------------------------------------------------------------------------
# DEFAULT AUTO FIELD
# ------------------------------------------------------------------------------------

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ------------------------------------------------------------------------------------
# for settings import
# ------------------------------------------------------------------------------------

RESEND_API_KEY = os.getenv("RESEND_API_KEY")

if not RESEND_API_KEY:
    raise RuntimeError("RESEND_API_KEY is not set")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY is not set")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} "
            "(pid={process:d} thread={thread:d}) "
            "{message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {},
}
