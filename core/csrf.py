"""CSRF failure response using the platform's public error envelope."""

from django.http import JsonResponse


def csrf_failure(request, reason=""):
    """Reject forged unsafe requests without disclosing CSRF internals."""
    return JsonResponse(
        {
            "success": False,
            "error": {
                "code": "CSRF_FAILED",
                "message": "CSRF validation failed.",
            },
        },
        status=403,
    )
