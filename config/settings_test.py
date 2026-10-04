"""Hermetic settings for the automated test suite.

Why this module exists
----------------------
`config.settings` calls ``load_dotenv()`` at import time, so a developer's
git-ignored ``backend/.env`` is visible to derived settings. ``settings_dev``
now requires the explicit development-only ``DEV_USE_REDIS_CACHE`` switch;
this module additionally pins LocMem so even that opt-in cannot alter tests.

That is not cosmetic.  The cache backend changes observable API behaviour:

    expired QR token -> LocMem: 404   (``qr_tokens.py:131-133``)
                       Redis:  409   (``qr_tokens.py:121-122``)

The documented command therefore produced different results on different
machines, and did not pin the contract it was supposed to be verifying.

This module pins the infrastructure the default gate runs against:

* cache  -> LocMemCache, unconditionally
* database -> SQLite, in-memory for the test run

``DEBUG`` stays ``True`` exactly as ``settings_dev`` sets it.  This is
deliberate: flipping it to ``False`` would set ``SESSION_COOKIE_SECURE`` and
``CSRF_COOKIE_SECURE`` to ``True``, and Django's test client speaks plain HTTP,
so the session cookie would be dropped and every authenticated test would fail
for a reason unrelated to the code under test.

Use this for the default gate::

    python manage.py test <app> --settings=config.settings_test

The PostgreSQL + Redis paths are a *separate*, explicit verification command --
see ``docs/IMPLEMENTATION_PLAN.md``. They exercise ``SELECT ... FOR UPDATE``,
the atomic Lua token consume, and the BR-029 concurrency tests that this module
deliberately leaves skipped.
"""

from .settings_dev import *  # noqa: F401,F403

# --- Pinned: cache backend -------------------------------------------------
# Unconditional, so no local .env can select Redis for the default gate.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fetplatform-tests",
    }
}

# --- Pinned: database ------------------------------------------------------
# SQLite for the run. ``:memory:`` keeps each test run isolated from
# backend/dev.sqlite3 and from any other process on the machine.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
        "TEST": {"NAME": ":memory:"},
    }
}

# --- Deterministic hashing -------------------------------------------------
# PBKDF2 at production iteration count costs ~14s per test on this machine
# (a full per-app suite takes 40-375s). The tests that care about hashing
# cost assert their own hasher; this keeps the gate runnable.
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# --- Test-only guarantees --------------------------------------------------
# ``USE_REDIS_CACHE`` in a local ``.env`` is deliberately ignored here so the
# gate stays hermetic. That is not a silent override: to exercise the
# production cache path, run ``--settings=config.settings`` (PostgreSQL +
# Redis) instead, which honours the flag and also un-skips the four BR-029
# concurrency tests. No warning is emitted on purpose -- a stderr warning
# breaks PowerShell pipelines, which reported a false non-zero exit for a
# fully green run.
