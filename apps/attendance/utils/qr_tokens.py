"""Shared, short-lived QR token mechanics for attendance.

This module deliberately makes no eligibility or authorization decision.  Its
job is limited to issuing short-lived random tokens and proving that a token
presented to the server was really issued by it.

Why validation does not consume
-------------------------------
A classroom QR is *shared* by design: one projected code, or one station's
code, must keep working for every student who scans it inside its TTL.  The MVP
mandate is explicit — a shared QR must not be globally consumed after the first
student, or the class behind them is locked out.  Replay therefore cannot be
solved by burning the token; it is solved by the layers around it:

* the token lives only ``QR_TOKEN_TTL_SECONDS`` (10s by default),
* it is bound to one session (and, for a station, one scan point),
* every scan is credited to the authenticated scanner and no one else, and
* a database UNIQUE(session, student) constraint makes a second credit for the
  same student impossible, no matter how many times the code is re-scanned.

So this module validates; ``attendance_service`` deduplicates.
"""

from __future__ import annotations

import json
import secrets
from typing import Any, Dict, Optional

from django.conf import settings
from django.core.cache import cache


class QRTokenError(ValueError):
    """Base error for token mechanics."""


class TokenExpiredError(QRTokenError):
    """The token is absent or its TTL has elapsed (BR-033)."""


class InvalidTokenError(QRTokenError):
    """The token payload is malformed or does not belong to this system."""


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
    both so the production path engages wherever Redis is configured; any
    other backend returns None and callers fall back to the Django cache API
    (single-process development/tests only).
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


def generate_token(*, session_id: Any, checkpoint_id: Any = None) -> str:
    """Issue a cryptographically random, TTL-bound token for one scan point.

    ``checkpoint_id`` present  -> STATION token (distributed stations mode).
    ``checkpoint_id`` absent   -> PROJECTOR token (projected code mode).

    The scope is derived server-side from where the request came from; no
    client-supplied field ever decides it.
    """
    if session_id is None:
        raise InvalidTokenError("Session is required")

    token = secrets.token_urlsafe(32)
    payload: Dict[str, str] = {"session_id": str(session_id)}
    if checkpoint_id is not None:
        payload["checkpoint_id"] = str(checkpoint_id)
        payload["scope"] = "STATION"
    else:
        payload["scope"] = "PROJECTOR"

    ttl = get_qr_token_ttl_seconds()
    key = _key(token)
    client = _redis_client()
    if client is not None:
        # Redis SET with NX and expiry avoids a cache serialization dependency.
        if not client.set(key, json.dumps(payload), ex=ttl, nx=True):  # pragma: no cover - astronomically unlikely
            return generate_token(session_id=session_id, checkpoint_id=checkpoint_id)
    else:
        # Development/test simulation only.
        cache.set(key, payload, timeout=ttl)
    return token


def validate_token(token: str) -> Dict[str, str]:
    """Return the payload of a live token without consuming it.

    Raises:
        TokenExpiredError: never issued, empty, or TTL elapsed (404).
        InvalidTokenError: stored payload is unreadable (404).

    Repeated validation of the same live token is expected and safe: the
    caller, not the token, is the identity, and the caller can only ever be
    credited once per session.
    """
    if not token or not isinstance(token, str):
        raise TokenExpiredError("Attendance token is missing or expired")

    key = _key(token)
    client = _redis_client()
    if client is not None:
        raw = client.get(key)
        if raw is None:
            raise TokenExpiredError("Attendance token is missing or expired")
        try:
            return json.loads(raw)
        except (TypeError, ValueError) as exc:  # pragma: no cover - cache corruption
            raise InvalidTokenError("Attendance token payload is invalid") from exc

    payload = cache.get(key)
    if payload is None:
        raise TokenExpiredError("Attendance token is missing or expired")
    if isinstance(payload, str):
        try:
            return json.loads(payload)
        except ValueError as exc:  # pragma: no cover - cache corruption
            raise InvalidTokenError("Attendance token payload is invalid") from exc
    return payload
