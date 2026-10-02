"""Custom DRF exception handler — wraps all errors in the standard
{"success": false, "error": {"code": ..., "message": ...}} envelope.

@module core.exception_handlers
"""

from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """Wrap DRF's default responses in the project-standard error envelope."""
    response = exception_handler(exc, context)
    if response is None:
        return None

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
