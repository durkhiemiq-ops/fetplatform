import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is required")

DEBUG = os.environ.get("DEBUG", "False").lower() in {"true", "1", "yes"}

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "core",
    "apps.academic",
    "apps.accounts",
    "apps.attendance",
    "apps.announcements",
    "apps.assessments",
    "apps.projects",
    "apps.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache" if DEBUG
        else "django_redis.cache.RedisCache",
        "LOCATION": "fetplatform" if DEBUG
        else os.getenv("REDIS_URL", "redis://localhost:6379/0"),
    }
}

# Opt into the real Redis cache even with DEBUG=True (local runs of these
# production settings against the Redis container — same flag settings_dev
# honors).  Without the flag, DEBUG decides exactly as before:
#   PowerShell:  $env:USE_REDIS_CACHE = "1"
if os.environ.get("USE_REDIS_CACHE", "").lower() in {"1", "true", "yes"}:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": os.getenv("REDIS_URL", "redis://localhost:6379/0"),
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "accounts.User"

# BR-001/BR-002/BR-170: identity resolution is owned by FlexibleLoginBackend,
# which resolves email, matricule, staffid (and the `username` column, via the
# email/matricule/staffid union) and FAILS CLOSED when an identifier is
# ambiguous.
#
# `django.contrib.auth.backends.ModelBackend` is deliberately NOT listed.
# It was a redundant fallback, but it is dangerous here: it resolves via
# `User._default_manager.get_by_natural_key(...)` -> `.get()`, which raises
# MultipleObjectsReturned if the username lookup is ever ambiguous, and Django
# lets that exception escape rather than treating it as a failed login. That
# turned a data-integrity fault into a 500 on the login endpoint.
AUTHENTICATION_BACKENDS = [
    "apps.accounts.backends.FlexibleLoginBackend",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "30/minute",
        "user": "60/minute",
        "login": "10/minute",
        "register": "5/minute",
        "verify-email": "10/minute",
        "resend-verification": "3/minute",
        # Item 1 resolution (API spec §50 + BR-203, BR-029): the scan scope is
        # per-AUTHENTICATED-STUDENT, never a shared endpoint budget.
        # ScopedRateThrottle keys on request.user.pk, so 100 different students
        # scanning in the same seconds each draw from their own 20/minute
        # allowance; only one student hammering the endpoint ever sees 429.
        "attendance-scan": "20/minute",
        # API §50 / BR-203: notification read-state mutation is idempotent and
        # not part of the sensitive surface, but a shared per-user budget keeps
        # bulk read-all spam bounded.  ScopedRateThrottle keys on user.pk.
        "notifications": "120/minute",
    },
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "core.exception_handlers.custom_exception_handler",
}

# Session security (BR-200: session cookies are HTTP-only)
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SECURE = not DEBUG  # BR-200: secure cookies in production
SESSION_COOKIE_AGE = 86400  # 24 hours
SESSION_SAVE_EVERY_REQUEST = False
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

CSRF_COOKIE_HTTPONLY = False  # JS needs to read CSRF token for DRF browsable API
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SECURE = not DEBUG  # BR-200: secure cookies in production
CSRF_FAILURE_VIEW = "core.csrf.csrf_failure"

# ===== Attendance timing — RESOLVED single source of truth =====
# QR token TTL (10s) and attendance-session window (60s) are the resolved
# defaults for the MVP.  These values are the authoritative ones; the
# Attendance & MVP Scope PDF's "~1-3 minutes" session window and "3m"
# Redis session-window TTL are proposal-stage estimates, not the rules.
#
# Why the Business Rules values win:
#   - Business Rules BR-035/BR-036 and §28 are the normative behavior spec:
#     "proposed default ... 10 seconds" and "proposed MVP duration ...
#     60 seconds", both explicitly "configurable without a software redesign".
#   - MVP Scope §2.1 "open for ~1-3 minutes" is a range description, and §7
#     "3m TTL" refers to the Redis session-cache retention — an infrastructure
#     floor that must simply stay >= the session window, not the check-in
#     window itself.  Session truth lives in PostgreSQL (per §27: Redis is
#     temporary; postgres is the permanent record), so the DB-sourced session
#     expiry is the defensible interpretation.
#   - Per Business Rules §30, academic data integrity outranks convenience:
#     a shorter default window is the safer MVP default and still allows a
#     lecturer to pick up to 10 minutes (see ATTENDANCE_SESSION_MAX_SECONDS).
# Flagged for product/security owner confirmation (BR-032 / handoff note):
# changing the *default* check-in window means changing
# ATTENDANCE_SESSION_TTL_SECONDS (or the lecturer default duration); the QR
# 10s TTL is not part of that decision.
QR_TOKEN_TTL_SECONDS = int(os.environ.get("QR_TOKEN_TTL_SECONDS", "10"))
ATTENDANCE_SESSION_TTL_SECONDS = int(os.environ.get("ATTENDANCE_SESSION_TTL_SECONDS", "60"))

# File upload limits (BR-183)
MAX_FILE_SIZE_BYTES = int(os.environ.get("MAX_FILE_SIZE_BYTES", "26214400"))  # 25 MB

# ===== Email delivery (OTP verification) =====
# Console backend is the safe development default: codes print to the
# runserver output instead of reaching a real mailbox.  Production sets
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend plus SMTP values.
EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "True").lower() in {"true", "1", "yes"}
DEFAULT_FROM_EMAIL = os.environ.get(
    "DEFAULT_FROM_EMAIL", "noreply@fetplatform.local"
)

# Email verification OTP — short-lived single-use secret (settings-driven TTL,
# same discipline as QR_TOKEN_TTL_SECONDS; never hardcoded in the views).
EMAIL_OTP_TTL_SECONDS = int(os.environ.get("EMAIL_OTP_TTL_SECONDS", "600"))  # 10 minutes
EMAIL_OTP_MAX_ATTEMPTS = int(os.environ.get("EMAIL_OTP_MAX_ATTEMPTS", "5"))

# ===== CORS Configuration (Frontend-Backend Integration) =====
CORS_ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:3000",
    ).split(",")
    if origin.strip()
]
CORS_ALLOW_CREDENTIALS = True

# CSRF trusted origins must match CORS_ALLOWED_ORIGINS for cross-origin session auth
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get(
        "CSRF_TRUSTED_ORIGINS",
        "http://localhost:3000",
    ).split(",")
    if origin.strip()
]
