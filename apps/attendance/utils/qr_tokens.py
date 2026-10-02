"""One-time QR token mechanics for attendance.

This module deliberately makes no eligibility or authorization decision.  Its
job is limited to issuing short-lived random tokens and atomically consuming
them exactly once.
"""

from __future__ import annotations

import json
import secrets
import threading
from datetime import timedelta
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache

from core.common import utc_now


class QRTokenError(ValueError):
    """Base error for token mechanics."""


class TokenExpiredError(QRTokenError):
    """The token is absent or its TTL has elapsed (BR-033)."""


class TokenAlreadyUsedError(QRTokenError):
    """The token has already been atomically consumed (BR-038)."""


class InvalidTokenError(QRTokenError):
    """The token payload is malformed or does not belong to this system."""


_LOCAL_TOKEN_LOCK = threading.Lock()
_LOCAL_USED_KEYS: set[str] = set()


def get_qr_token_ttl_seconds() -> int:
    """Return the confirmed BR-035 default: ten seconds."""
    ttl = int(getattr(settings, "QR_TOKEN_TTL_SECONDS", 10))
    if ttl <= 0:
        raise InvalidTokenError("QR token TTL must be positive")
    return ttl


def _key(token: str) -> str:
    return f"attendance:qr:{token}"


def _redis_client() -> Optional[Any]:
    """Return a raw Redis client only for Django's Redis cache backend.

    django_redis exposes the raw client differently across versions: older
    releases put ``get_client`` on the ``RedisCache`` backend itself, 7.x
    wraps it in a ``DefaultClient`` reachable as ``backend.client``.  Probe
    both so the production atomic path engages wherever Redis is configured;
    any other backend returns None and callers fall back to the Django cache
    API (single-process development/tests only).
    """
    backend = getattr(cache, "_cache", None)
    if backend is None:
        try:
            backend = cache._connections[cache._alias]
        except (AttributeError, KeyError, TypeError, IndexError):
            return None
    if backend is None:
        return None
    target = getattr(backend, "client", None) or backend
    if not hasattr(target, "get_client"):
        return None
    try:
        return target.get_client(write=True)
    except Exception:  # pragma: no cover - connection setup failures
        return None


def generate_token(*, checkpoint_id: Any, session_id: Any) -> str:
    """Issue a cryptographically random, TTL-bound checkpoint token."""
    if checkpoint_id is None or session_id is None:
        raise InvalidTokenError("Checkpoint and session are required")

    token = secrets.token_urlsafe(32)
    payload = {"checkpoint_id": str(checkpoint_id), "session_id": str(session_id)}
    ttl = get_qr_token_ttl_seconds()
    key = _key(token)
    client = _redis_client()
    if client is not None:
        # Redis SET with NX and expiry avoids a cache serialization dependency.
        if not client.set(key, json.dumps(payload), ex=ttl, nx=True):  # pragma: no cover - astronomically unlikely
            return generate_token(checkpoint_id=checkpoint_id, session_id=session_id)
    else:
        # Development/test simulation only.  The lock provides atomicity in one
        # process; production must use Redis for multi-worker atomicity.
        cache.set(key, payload, timeout=ttl)
    return token


def consume_token(token: str) -> Dict[str, str]:
    """Atomically retrieve and invalidate a one-time token.

    Redis uses one Lua operation (GET then DEL in one server-side command).
    The local development cache uses one process lock.  There is deliberately
    no read-then-write path that could let two simultaneous scans succeed.
    """
    if not token or not isinstance(token, str):
        raise TokenExpiredError("Attendance token is missing or expired")

    key = _key(token)
    client = _redis_client()
    if client is not None:
        raw = client.eval(
            "local value = redis.call('GET', KEYS[1]); "
            "if value then redis.call('DEL', KEYS[1]); end; return value",
            1,
            key,
        )
        if raw is None:
            raise TokenAlreadyUsedError("Attendance token was already used or expired")
        try:
            return json.loads(raw)
        except (TypeError, ValueError) as exc:  # pragma: no cover - cache corruption
            raise InvalidTokenError("Attendance token payload is invalid") from exc

    with _LOCAL_TOKEN_LOCK:
        if key in _LOCAL_USED_KEYS:
            raise TokenAlreadyUsedError("Attendance token was already used")
        payload = cache.get(key)
        if payload is None:
            raise TokenExpiredError("Attendance token is missing or expired")
        cache.delete(key)
        _LOCAL_USED_KEYS.add(key)
        return payload


def validate_token(token: str) -> Dict[str, str]:
    """Backward-compatible public name; validation consumes the token once."""
    return consume_token(token)
