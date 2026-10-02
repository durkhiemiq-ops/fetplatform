"""Custom DRF exception handler — wraps all errors in the standard
{"success": false, "error": {"code": ..., "message": ...}} envelope.

@module core.exception_handlers
"""

import logging

from django.http import Http404
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)

#: Returned for any unexpected server-side failure. Deliberately opaque: it is
#: identical whether the request ran with DEBUG=True or False, so enabling DEBUG
#: on a developer machine cannot turn a 500 into a data leak on a shared one.
INTERNAL_ERROR_MESSAGE = "An unexpected error occurred. Please try again."


def custom_exception_handler(exc, context):
    """Wrap DRF's default responses in the project-standard error envelope.

    Every response this project emits uses the envelope — including 500s.
    Returning ``None`` for a non-``APIException`` used to hand the response back
    to Django, which rendered an HTML traceback page instead, breaking the
    contract the frontend parses and leaking internals under ``DEBUG=True``.
    """
    response = exception_handler(exc, context)
    if response is None:
        # Django's own Http404 is converted by DRF above, so anything landing
        # here is genuinely unexpected (ValueError, database errors, ...).
        # Log it with a traceback for operators; never return the detail.
        if isinstance(exc, Http404):  # pragma: no cover - DRF handles these
            return Response(
                {"success": False, "error": {"code": "NOT_FOUND", "message": "Not found."}},
                status=404,
            )
        logger.exception(
            "Unhandled exception in %s",
            (context or {}).get("view", type(exc).__name__),
        )
        return Response(
            {
                "success": False,
                "error": {"code": "SERVER_ERROR", "message": INTERNAL_ERROR_MESSAGE},
            },
            status=500,
        )

    # Determine error code from status code.
    # BR-203: 400 responses (validation failures AND indistinguishable
    # duplicates) share the same code so attackers cannot enumerate
    # registered emails by observing a distinct response.
    status_code = response.status_code
    if status_code == 400:
        code = "INVALID_DATA"
    elif status_code == 401:
        code = "UNAUTHENTICATED"
    elif status_code == 403:
        code = "FORBIDDEN"
    elif status_code == 404:
        code = "NOT_FOUND"
    elif status_code == 405:
        code = "METHOD_NOT_ALLOWED"
    elif status_code == 429:
        code = "RATE_LIMITED"
    elif status_code >= 500:
        code = "SERVER_ERROR"
    else:
        code = "ERROR"

    # Flatten DRF's field-level errors into a single message
    # e.g. {"email": ["invalid"], "password": ["too short"]} -> "email: invalid; password: too short"
    detail = response.data
    if isinstance(detail, dict):
        parts = []
        for field, messages in detail.items():
            msg_list = messages if isinstance(messages, list) else [messages]
            for msg in msg_list:
                parts.append(f"{field}: {msg}" if field != "detail" else str(msg))
        message = "; ".join(parts) if parts else str(detail)
    elif isinstance(detail, list):
        message = "; ".join(str(m) for m in detail)
    else:
        message = str(detail)

    response.data = {
        "success": False,
        "error": {
            "code": code,
            "message": message,
        },
    }
    return response
