"""Shared anonymous recovery views, mounted under accounts and auth aliases."""

from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .serializers import StrictPublicFieldsMixin
from .services.password_reset import (
    REQUEST_MESSAGE, ResetCredentialError, ResetPasswordPolicyError,
    request_password_reset, reset_password,
)


class RecoveryRequestThrottle(AnonRateThrottle):
    scope = "password-reset-request"
    rate = "3/minute"


class RecoveryAttemptThrottle(AnonRateThrottle):
    scope = "password-reset-attempt"
    rate = "10/minute"


class RequestSerializer(StrictPublicFieldsMixin, serializers.Serializer):
    email = serializers.EmailField(max_length=254)


class ResetSerializer(RequestSerializer):
    code = serializers.CharField(max_length=128, trim_whitespace=False)
    new_password = serializers.CharField(write_only=True, min_length=1, max_length=1024, trim_whitespace=False)


class ForgotPasswordView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [RecoveryRequestThrottle]

    def post(self, request):
        serializer = RequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        request_password_reset(**serializer.validated_data)
        return Response({"success": True, "data": {"message": REQUEST_MESSAGE}})


class ResetPasswordView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [RecoveryAttemptThrottle]

    def post(self, request):
        serializer = ResetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            reset_password(**serializer.validated_data)
        except ResetCredentialError as exc:
            return Response({"success": False, "error": {"code": "RESET_FAILED", "message": str(exc)}}, status=400)
        except ResetPasswordPolicyError as exc:
            return Response({"success": False, "error": {"code": "INVALID_PASSWORD", "message": str(exc)}}, status=400)
        return Response({"success": True, "data": {"message": "Password updated. Sign in with your new password."}})
