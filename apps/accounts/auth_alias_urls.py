"""Compatibility adapter: ``/api/v1/auth/*`` -> canonical account views.

The integrated frontend addresses session authentication below ``/auth/``. This
module re-points those paths at the views that already own the behaviour, so
the two namespaces cannot drift apart in authorization, audit logging, or the
response envelope. It deliberately contains no business logic.

Registration **is** exposed here (``register/`` and ``self-register/``): both
are thin aliases onto the single canonical ``SelfRegisterView``, which is the
only place that decides a new account's role and approval status. Anonymous
callers may therefore create an account through either namespace, but no field
they send can choose a role or grant a privilege.

Permission classes are inherited unchanged from the views these routes alias,
so the classification documented in ``apps/accounts/urls.py`` applies to both
namespaces.

Why ``refresh/`` exists at all
------------------------------
This backend authenticates with a Django session cookie, not a short-lived
JWT, so there is no access token to refresh. The frontend's axios interceptor
(``src/lib/api.js``) calls ``/auth/refresh/`` once on any 401 and retries the
request. Requiring ``IsAuthenticated`` keeps that retry honest: a genuinely dead
session still yields 401, so the client clears its cached auth state and
redirects to /login, exactly as it would against a real refresh endpoint.
"""

from django.urls import path
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from . import views
from .recovery_views import ForgotPasswordView, ResetPasswordView
from .services.auth_service import (
    InvalidCurrentPasswordError,
    PasswordPolicyError,
    change_account_password,
)
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

        try:
            user = change_account_password(
                account=request.user,
                current_password=current_password,
                new_password=new_password,
            )
        except InvalidCurrentPasswordError as exc:
            return _error_response(
                str(exc),
                "INVALID_CREDENTIALS",
                status.HTTP_400_BAD_REQUEST,
            )
        except PasswordPolicyError as exc:
            return _error_response(
                str(exc),
                "VALIDATION_ERROR",
                status.HTTP_400_BAD_REQUEST,
            )

        # Keep this browser signed in with the new auth hash. Other sessions
        # retain the old hash and are rejected on their next request.
        from django.contrib import auth

        auth.update_session_auth_hash(request, user)

        return _success_response({"message": "Password updated."})


urlpatterns = [
    path("forgot-password/", ForgotPasswordView.as_view(), name="auth-forgot-password"),
    path("reset-password/", ResetPasswordView.as_view(), name="auth-reset-password"),
    path("resend-verification/", views.ResendVerificationView.as_view(), name="auth-resend-verification"),
    path("login/", views.LoginView.as_view(), name="auth-login"),
    path("logout/", views.LogoutView.as_view(), name="auth-logout"),
    path("me/", views.CurrentUserView.as_view(), name="auth-me"),
    # Thin aliases onto the single canonical SelfRegisterView, so the two
    # namespaces can never drift apart in behaviour.
    path("register/", views.SelfRegisterView.as_view(), name="auth-register"),
    path(
        "self-register/", views.SelfRegisterView.as_view(), name="auth-self-register"
    ),
    path("verify-email/", views.VerifyEmailView.as_view(), name="auth-verify-email"),
    path("change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("refresh/", SessionRefreshView.as_view(), name="auth-refresh"),
]
