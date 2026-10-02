import logging

from django.contrib import auth
from django.http import JsonResponse
from django.middleware.csrf import get_token
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle
from rest_framework.views import APIView

from core.academic_access import is_admin_user, is_authorized_academic_user
from core.audit import write_audit_entry

from .models import User
from .serializers import (
    ChangeRoleSerializer,
    LoginSerializer,
    RegisterSerializer,
    UserSerializer,
)
from .services.auth_service import (
    AuthError,
    DuplicateAccountError,
    InvalidRoleError,
    SelfRoleAssignmentError,
    UnauthorizedRoleChangeError,
    register_account,
    change_user_role,
)
from .services.email_otp import (
    OTPResult,
    issue_otp,
    send_verification_email,
    verify_otp,
)

logger = logging.getLogger(__name__)


def _error_response(message, code, http_status=status.HTTP_400_BAD_REQUEST):
    return Response(
        {"success": False, "error": {"code": code, "message": message}},
        status=http_status,
    )


def _success_response(data, http_status=status.HTTP_200_OK):
    return Response({"success": True, "data": data}, status=http_status)


def csrf_token_view(request):
    """Return the CSRF token. The token is also set as a cookie by Django's CsrfViewMiddleware."""
    token = get_token(request)
    return JsonResponse({"success": True, "data": {"csrfToken": token}})


class RegisterView(APIView):
    permission_classes = []
    authentication_classes = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            account = register_account(
                email=data["email"],
                username=data["username"],
                first_name=data["first_name"],
                last_name=data["last_name"],
                password=data["password"],
                AccountModel=User,
            )
        except DuplicateAccountError:
            # BR-203: uniform response — indistinguishable from a validation error
            # so attackers cannot enumerate valid email addresses.
            return _error_response(
                "Registration failed. Please check your details.",
                "INVALID_DATA",
                status.HTTP_400_BAD_REQUEST,
            )
        except AuthError as exc:
            return _error_response(str(exc), "INVALID_DATA", status.HTTP_400_BAD_REQUEST)

        # OTP delivery: issue a one-time code and email it now.  The account
        # already exists at this point, so a delivery failure must not become
        # a 500 — resend-verification is the recovery path.  The code is a
        # live secret: only its generic failure mode may ever be logged.
        try:
            code = issue_otp(account.email)
            send_verification_email(account.email, code)
        except Exception as exc:  # noqa: BLE001 - delivery must not fail signup
            logger.warning(
                "verification email dispatch failed for account %s (%s)",
                account.id,
                type(exc).__name__,
            )

        return _success_response(
            UserSerializer(account).data,
            status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    permission_classes = []
    authentication_classes = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        login_identifier = data["login_identifier"]
        password = data["password"]

        # Resolve the user by email, matricule, or staffid.
        user = auth.authenticate(
            request,
            username=login_identifier,
            password=password,
        )
        if user is None:
            return _error_response(
                "Invalid credentials.",
                "INVALID_CREDENTIALS",
                status.HTTP_401_UNAUTHORIZED,
            )
        if not user.is_active:
            return _error_response(
                "This account has been disabled.",
                "ACCOUNT_DISABLED",
                status.HTTP_403_FORBIDDEN,
            )
        if not user.is_email_verified:
            # Product decision: unverified accounts never establish a session
            # (one gate, mirroring ACCOUNT_DISABLED).  Reached only after
            # credentials already matched, so it cannot enumerate addresses.
            return _error_response(
                "Please verify your email address before signing in.",
                "ACCOUNT_NOT_VERIFIED",
                status.HTTP_403_FORBIDDEN,
            )

        auth.login(request, user)
        return _success_response(UserSerializer(user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        auth.logout(request)
        return _success_response({"message": "Logged out successfully."})


class CurrentUserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _success_response(UserSerializer(request.user).data)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return _success_response(serializer.data)


class ChangeRoleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not is_admin_user(request.user):
            return _error_response(
                "Only administrators may change user roles.",
                "UNAUTHORIZED_ROLE_CHANGE",
                status.HTTP_403_FORBIDDEN,
            )

        serializer = ChangeRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            target_user = User.objects.get(id=data["user_id"])
        except User.DoesNotExist:
            return _error_response(
                "User not found.",
                "USER_NOT_FOUND",
                status.HTTP_404_NOT_FOUND,
            )

        try:
            change_user_role(
                target_user,
                data["new_role"],
                actor=request.user,
            )
        except SelfRoleAssignmentError as exc:
            return _error_response(
                str(exc), "SELF_ROLE_ASSIGNMENT", status.HTTP_403_FORBIDDEN
            )
        except UnauthorizedRoleChangeError as exc:
            return _error_response(
                str(exc), "UNAUTHORIZED_ROLE_CHANGE", status.HTTP_403_FORBIDDEN
            )
        except InvalidRoleError as exc:
            return _error_response(
                str(exc), "INVALID_ROLE", status.HTTP_400_BAD_REQUEST
            )

        return _success_response(UserSerializer(target_user).data)


class UserListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_admin_user(request.user):
            return _error_response(
                "Only administrators may list users.",
                "UNAUTHORIZED",
                status.HTTP_403_FORBIDDEN,
            )

        users = User.objects.all()
        return _success_response(UserSerializer(users, many=True).data)


class VerifyEmailView(APIView):
    """Consume the one-time code issued at registration.

    Unauthenticated by design: a user who cannot log in yet must still be
    able to verify.  Every failure — wrong code, expired or absent code,
    unknown address, malformed body — returns one identical response, so
    this endpoint can never serve as an email-enumeration oracle (BR-203
    discipline, applied to OTP verification exactly as to registration).
    """

    authentication_classes = []
    permission_classes = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "verify-email"

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        email = str(data.get("email") or "").strip().lower()
        code = str(data.get("code") or "").strip()

        if email and code and verify_otp(email, code) is OTPResult.VERIFIED:
            user = User.objects.filter(email__iexact=email).first()
            if user is not None:
                if not user.is_email_verified:
                    user.is_email_verified = True
                    user.save(update_fields=["is_email_verified"])
                    # BR-210: verification flips a security-relevant account
                    # state and must be traceable like a role change.
                    write_audit_entry(
                        action="email_verified",
                        resource_type="account",
                        resource_id=user.id,
                        actor_id=user.id,
                        old_value=False,
                        new_value=True,
                    )
                return _success_response({"message": "Email verified."})

        # One generic failure for every failure mode — see class docstring.
        return _error_response(
            "Verification failed. Request a new code and try again.",
            "VERIFICATION_FAILED",
            status.HTTP_400_BAD_REQUEST,
        )


class ResendVerificationView(APIView):
    """Dispatch a fresh code for an address awaiting verification.

    The response is identical whether or not such an account exists — the
    endpoint must never confirm an address is registered — while a fresh
    code atomically kills the previous one.  Its own throttle scope ships
    from day one: this endpoint triggers a paid side effect (email
    delivery) and would otherwise be an inbox-flood and cost vector.
    """

    authentication_classes = []
    permission_classes = []
    throttle_classes = [AnonRateThrottle, ScopedRateThrottle]
    throttle_scope = "resend-verification"

    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        email = str(data.get("email") or "").strip().lower()
        if email:
            user = User.objects.filter(email__iexact=email).first()
            if user is not None and not user.is_email_verified:
                try:
                    code = issue_otp(user.email)
                    send_verification_email(user.email, code)
                except Exception as exc:  # noqa: BLE001 - generic response either way
                    logger.warning(
                        "verification resend dispatch failed for account %s (%s)",
                        user.id,
                        type(exc).__name__,
                    )
        return _success_response(
            {
                "message": (
                    "If that address is awaiting verification, "
                    "a new code has been sent."
                )
            }
        )


class StudentListView(APIView):
    """Academic-readable student directory for assessment and member pickers.

    The general user list (/accounts/) is administrator-only; lecturers need
    this narrower view to choose students when creating assessments or
    assigning them to projects.  Only identity fields are returned — no
    emails, matricules, or other personal data beyond names.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not is_authorized_academic_user(request.user):
            return _error_response(
                "Only academic users may list students.",
                "UNAUTHORIZED",
                status.HTTP_403_FORBIDDEN,
            )

        students = User.objects.filter(role=User.Role.STUDENT).order_by(
            "first_name", "last_name", "username"
        )
        rows = [
            {
                "id": student.id,
                "first_name": student.first_name,
                "last_name": student.last_name,
                "username": student.username,
            }
            for student in students
        ]
        return _success_response(rows)
