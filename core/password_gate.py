"""Global first-login password gate for institution-provisioned accounts."""

from django.http import JsonResponse


class RequirePasswordChangeMiddleware:
    """Deny application access until a roster temporary password is replaced."""

    allowed_paths = frozenset(
        {
            "/api/v1/auth/me/",
            "/api/v1/auth/logout/",
            "/api/v1/auth/refresh/",
            "/api/v1/auth/change-password/",
            "/api/v1/accounts/csrf/",
        }
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and getattr(user, "must_change_password", False)
            and request.path not in self.allowed_paths
        ):
            return JsonResponse(
                {
                    "success": False,
                    "error": {
                        "code": "PASSWORD_CHANGE_REQUIRED",
                        "message": "Change the temporary password before continuing.",
                    },
                },
                status=403,
            )
        return self.get_response(request)
