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
    "django.contrib.sitemaps",
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

# Staged Assisted workflows (ai.services.workflow). Budgets count *logical*
# provider calls per stage across the whole run unless scoped (see the
# Reconcile notes below; a correction or a review-driven re-plan both consume
# from the stage's own budget);
# OpenAIProvider's internal transport retries (AI_MAX_PROVIDER_RETRIES) are
# not logical calls and never count here.
AI_CREATE_PLANNING_MAX_CALLS = 3
# Reconcile (ai/README.md): Extraction batches (intent framing + evidence
# claims; small evidence is one batch) and their item/segment-level
# correction calls, typed Adjudication rounds (and their correction calls),
# Gap Probe rounds (and their correction calls) for unsatisfied structural
# requirements, and Verification reviews (and the re-ask of an unroutable
# objection). The workflow converges by revisiting stages (a probe's claims
# may raise new questions, an answer may expose a new evidence gap), so every
# class of work is bounded separately: corrections never consume rounds.
# Correction budgets of Extraction, Adjudication and Gap Probe count per unit
# of new work (a correction wave / a round), never per run, so earlier work
# can't spend a later round's chance to be corrected. Adjudication and Gap
# Probe rounds are progress-driven, not counted: they continue while there is
# new work, until a class has spent MAX_IDLE_ROUNDS consecutive rounds without
# progress, and only while the run's remaining calls still cover a full
# Verification pass (ai.services.stages.reconcile_steps).
AI_RECONCILE_EXTRACTION_MAX_BATCHES = 4
AI_RECONCILE_EXTRACTION_MAX_CORRECTION_CALLS = 2  # per correction wave
AI_RECONCILE_ADJUDICATION_MAX_CORRECTION_CALLS = 1  # per round
AI_RECONCILE_ADJUDICATION_MAX_IDLE_ROUNDS = 2
AI_RECONCILE_GAP_PROBE_MAX_CORRECTION_CALLS = 1  # per round
AI_RECONCILE_GAP_PROBE_MAX_IDLE_ROUNDS = 2
AI_RECONCILE_VERIFICATION_MAX_CALLS = 3
AI_RECONCILE_VERIFICATION_MAX_CORRECTION_CALLS = 1
# Reconcile's evidence architecture (.Documentation/reconcile-architecture-plan.md):
#   claims   -- the AI extracts per-instance claims from every segment (legacy)
#   readings -- tables and sections are interpreted ONCE per schema by a
#               Reading (ai.services.reconcile.readings) and expanded
#               deterministically; the AI extracts claims from prose only
# readings is the default since 2026-10-09: the live flyer gate passed the full
# reference spec in 3/5 readings-mode runs with zero forbidden changes
# (.ai-traces/gate-2026-10-09-flyer-readings-4). claims stays available
# (AI_RECONCILE_EVIDENCE_MODE=claims) until Phase 6 retires it.
AI_RECONCILE_EVIDENCE_MODE = os.getenv("AI_RECONCILE_EVIDENCE_MODE", "readings")
# Reading: bounded batches of structured elements (AI cost scales with the
# number of table/section schemas, never rows), one shape re-ask per batch,
# and how many sample rows of a table a Reading is shown (all when fewer;
# structural outlier rows are always shown in addition).
AI_RECONCILE_READING_MAX_BATCHES = 4
AI_RECONCILE_READING_MAX_CORRECTION_CALLS = 1  # per batch
AI_READING_BATCH_MAX_CHARS = 12_000
AI_READING_SAMPLE_ROWS = 8
# Ranked options offered per Reading slot (a shortlist only: any catalogue key
# outside it may still be named and is validated against the full catalogue).
AI_READING_MAX_OPTIONS = 20
# Hard backstop on logical workflow calls for any one run, whatever the
# per-stage budgets add up to.
AI_WORKFLOW_MAX_PROVIDER_CALLS = 14
# Readings-mode Reconcile scales that backstop with the workload it plans
# (ai.services.stages.reconcile_steps.workload_allowance): Reading and
# Extraction calls are not checked against a reserve for the later stages,
# so a larger document gets the calls its extra batches may cost --
#     allowance = 2 * max(0, R - 2) + max(0, E - 1)
# (R / E = planned Reading / Extraction batches, each capped by its stage
# limit; a Reading batch may cost its call plus one correction). 14 is
# calibrated on the international flyer (R=2, E=1), which keeps >= 7 calls
# after the worst-case unchecked pre-analysis work (2R + E + 2); the
# allowance keeps that reserve for every larger workload. 7 covers every
# workload the batch limits above permit (R, E <= 4). A workload needing more
# is granted this cap and reported (ReconcileState.budget_shortfall).
AI_WORKFLOW_MAX_EXTRA_PROVIDER_CALLS = 7
# Opt-in, dev-only run tracing (ai.services.tracing): when active, every
# step's payload/output and Reconcile state snapshot is written as JSON
# under this directory. Never stored in the database; unset by default.
AI_TRACE_DIR = os.getenv("AI_TRACE_DIR") or None
# A further, independently-overridable switch over AI_TRACE_DIR (e.g. to
# force tracing off in CI without touching AI_TRACE_DIR). Defaults on:
# setting AI_TRACE_DIR is already an explicit, dev-only opt-in, so this adds
# a second manual step only when someone wants one.
RECONCILE_TRACE_ENABLED = os.getenv("RECONCILE_TRACE_ENABLED", "true").lower() == "true"
# The actual invariant -- DEBUG=False always wins, whatever the flags above
# say -- is enforced dynamically by ai.services.tracing.trace_active() (so
# `override_settings` in tests behaves normally); this just documents it.
RECONCILE_TRACE_ACTIVE = DEBUG and RECONCILE_TRACE_ENABLED and bool(AI_TRACE_DIR)
# Deterministic (non-provider) workflow steps any one run may take -- a
# backstop against a routing loop, never reached by a well-formed run.
AI_WORKFLOW_MAX_DETERMINISTIC_STEPS = 40
# The terminal explain()-only call on an UNRESOLVED run sits OUTSIDE the
# workflow budget above, under its own cap -- so the absolute per-run
# ceiling is AI_WORKFLOW_MAX_PROVIDER_CALLS + AI_TERMINAL_EXPLANATION_MAX_CALLS.
AI_TERMINAL_EXPLANATION_MAX_CALLS = 1

# Deterministic context sizing. AI_CONTEXT_MAX_OBJECTS bounds the records in
# any one semantic context; AI_CONTEXT_MAX_BYTES bounds its serialised size.
AI_CONTEXT_MAX_OBJECTS = 300
AI_CONTEXT_MAX_BYTES = 100_000
# EvidenceGraph bounds (entities + assertions + facts per graph).
AI_EVIDENCE_MAX_ITEMS = 300
AI_PROVENANCE_MAX_EXCERPT_CHARS = 500
# Structural options OnyxJar offers for one ambiguous mapping/identity
# question, and the evidence text a Gap Probe / Verification call may see.
AI_MAPPING_MAX_OPTIONS = 8
# Segment text per Extraction batch (evidence within one batch is extracted
# in a single call), per Gap Probe evidence pack, and per Verification call.
AI_EXTRACTION_BATCH_MAX_CHARS = 12_000
AI_GAP_PROBE_PACK_MAX_CHARS = 8_000
AI_VERIFY_EVIDENCE_MAX_CHARS = 24_000

# OJ feedback issues sent back to any one correction attempt, and findings
# kept on an AssistedTask.
AI_FEEDBACK_MAX_ISSUES = 30
AI_MAX_TASK_FINDINGS = 30

# ProposalChanges one AI operation's compiled ChangeSet may produce (same order of
# magnitude as IMPORT_MAX_CHANGES=1000; AI ChangeSets are expected far smaller).
AI_MAX_CHANGE_SET_ACTIONS = 100

# User-supplied intent text length.
AI_MAX_INTENT_CHARS = 4000

AI_PROVIDER_TIMEOUT_SECONDS = 60
AI_MAX_PROVIDER_RETRIES = 2

# Policy switch for the explain()-only call made when a staged workflow ends
# UNRESOLVED (see AI_TERMINAL_EXPLANATION_MAX_CALLS).
AI_FINAL_EXPLANATION_ENABLED = True

# ------------------------------------------------------------------------------------
# ASSISTED TASKS (assisted app)
# ------------------------------------------------------------------------------------

# How long a QUEUED AssistedTask may sit without reaching RUNNING before it's
# treated as a silently-failed-to-enqueue dispatch and lazily reclaimed the
# next time anything checks for an active task against its Model.
ASSISTED_TASK_QUEUED_STUCK_THRESHOLD = timedelta(minutes=5)

# How long a RUNNING AssistedTask may go without a heartbeat before it's
# treated as orphaned (its worker died) and lazily reclaimed the same way.
# Staged workflows heartbeat (AssistedTask.updated_at) before every provider
# call, so this measures inactivity, not total run time -- it only has to
# exceed one provider call's worst case (AI_PROVIDER_TIMEOUT_SECONDS x
# (AI_MAX_PROVIDER_RETRIES + 1)) plus deterministic staging/validation.
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
