"""Compatibility adapter: ``/api/v1/auth/*`` -> canonical account views.

The integrated frontend addresses session authentication below ``/auth/``.
Account creation is deliberately absent: institution roster workflows create
accounts and assign institutional identity; anonymous callers cannot create an
account or choose an identity through a compatibility alias.

This module deliberately contains **no business logic**. Every route delegates
to the view that already owns the behaviour, so authorization, audit logging
(BR-210), throttling and the response envelope stay in exactly one place.

Why ``refresh/`` exists at all
------------------------------
This backend authenticates with a Django session cookie, not a short-lived
JWT, so there is no access token to refresh. The frontend's axios interceptor
(``src/lib/api.js``) calls ``/auth/refresh/`` once on any 401 and retries the
request. Requiring ``IsAuthenticated`` keeps that retry honest: a genuinely dead
session still yields 401, so the client clears its cached auth state and
redirects to /login, exactly as it would against a real refresh endpoint.
"""

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.urls import path
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from . import views
from .views import _error_response, _success_response


class SessionRefreshView(APIView):
    """Stand-in for JWT refresh; reports success only while the session lives."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        return _success_response({"message": "Session still valid."})


class ChangePasswordView(APIView):
    """Password change for the current user, gated to an authenticated session.

    The frontend calls ``/auth/change-password/``; this backend had no
    equivalent. It validates against the project's configured password
    validators and requires the current password, so possession of a stolen
    session alone is not enough to take the account over.

    Deliberately narrow: it changes nothing but the password hash. Institution-
    assigned identity (email, matricule, staffid) and role stay behind
    ``POST /accounts/change-role/`` and admin flows, per the security note on
    ``UserSerializer``.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        new_password = str(request.data.get("new_password") or "")
        current_password = str(request.data.get("current_password") or "")

        if not new_password:
            return _error_response(
                "A new password is required.",
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
            )

        if not request.user.check_password(current_password):
            return _error_response(
                "Current password is incorrect.",
                "INVALID_CREDENTIALS",
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(new_password, request.user)
        except DjangoValidationError as exc:
            return _error_response(
                " ".join(exc.messages),
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
            )

        user = get_user_model().objects.get(pk=request.user.pk)
        user.set_password(new_password)
        user.save(update_fields=["password"])

        # Changing a password must invalidate the session it was changed from.
        from django.contrib import auth

        auth.update_session_auth_hash(request, user)

        return _success_response({"message": "Password updated."})


urlpatterns = [
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.CurrentUserView.as_view(), name="auth-me"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("refresh/", SessionRefreshView.as_view(), name="auth-refresh"),
]
