"""Global first-login password gate for institution-provisioned accounts."""

from django.http import JsonResponse


class RequirePasswordChangeMiddleware:
    """Deny application access until a roster temporary password is replaced."""

    #: Endpoints a gated account may still reach: read its own identity, replace
    #: the temporary password, keep the session alive, and sign out.
    #:
    #: Both URL namespaces are live — the canonical ``/api/v1/accounts/*`` and
    #: the ``/api/v1/auth/*`` compatibility aliases in
    #: ``apps.accounts.auth_alias_urls`` — so both must be listed. Omitting the
    #: canonical pair previously left a roster-provisioned user unable to read
    #: ``/accounts/me/`` (so the client could not even discover that it must
    #: change its password) and unable to log out at all, because the gate
    #: answers 403 before the view runs.
    allowed_paths = frozenset(
        {
            "/api/v1/auth/me/",
            "/api/v1/auth/logout/",
            "/api/v1/auth/refresh/",
            "/api/v1/auth/change-password/",
            "/api/v1/accounts/csrf/",
            "/api/v1/accounts/me/",
            "/api/v1/accounts/logout/",
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
