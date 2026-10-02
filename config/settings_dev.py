"""Local development settings with simulated infrastructure.

This module intentionally keeps the production PostgreSQL and Redis settings
untouched.  It is for running the account API locally when those services are
not configured on the developer machine.
"""

import os

from .settings import *  # noqa: F403


DEBUG = True
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "dev.sqlite3",  # noqa: F405
    }
}

# The local-memory cache simulates Redis only for single-process development.
# It must not be used for shared, multi-worker, or production deployments.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fetplatform-development",
    }
}

# Opt into the real Redis container (fetplatform-redis) to exercise the
# production cache path locally — QR tokens, OTP codes, DRF throttles, and
# the repeated-failure counters all run their Redis/Lua branches:
#   PowerShell:  $env:USE_REDIS_CACHE = "1"
#   then run manage.py / manage.py test as usual.
if os.environ.get("USE_REDIS_CACHE", "").lower() in {"1", "true", "yes"}:
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": os.environ.get("REDIS_URL", "redis://localhost:6379/0"),
        }
    }
