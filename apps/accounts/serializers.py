from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .models import User
from .services.registration_eligibility import (
    EligibilityError,
    normalize_account_type,
    validate_identity_free,
)


class StrictPublicFieldsMixin:
    """Reject claims the public endpoint does not explicitly accept."""

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object.")
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({name: "This field is not permitted." for name in sorted(unexpected)})
        return super().to_internal_value(data)


class SelfRegisterSerializer(StrictPublicFieldsMixin, serializers.Serializer):
    """Account type requests a student account or a pending lecturer application."""

    account_type = serializers.ChoiceField(choices=["student", "lecturer"])
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8, max_length=1024, trim_whitespace=False)
    matricule = serializers.CharField(max_length=50, required=False, allow_blank=True)

    def validate(self, attrs):
        try:
            attrs["account_type"] = normalize_account_type(attrs.get("account_type"))
            is_student = attrs["account_type"] == "student"
            if is_student and not str(attrs.get("matricule") or "").strip():
                raise serializers.ValidationError({"matricule": "Matricule number is required for students."})
            if not is_student and attrs.get("matricule"):
                raise serializers.ValidationError({"matricule": "This field is for student registration."})
            validate_identity_free(matricule=attrs.get("matricule"), staffid=None)
        except EligibilityError as exc:
            raise serializers.ValidationError({"account_type": str(exc)}) from exc
        return attrs


class LecturerApprovalDecisionSerializer(serializers.Serializer):
    """Administrator decision on a pending lecturer application."""

    decision = serializers.ChoiceField(choices=["approve", "reject"])
    reason = serializers.CharField(
        required=False, allow_blank=True, default="", max_length=500
    )


class RegisterSerializer(serializers.Serializer):
    email = serializers.EmailField()
    username = serializers.CharField(max_length=150)
    first_name = serializers.CharField(max_length=150)
    last_name = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_username(self, value):
        normalized = value.strip().lower()
        if User.objects.filter(username=normalized).exists():
            raise serializers.ValidationError("This username is already taken.")
        return normalized

    def validate(self, attrs):
        """Run the configured AUTH_PASSWORD_VALIDATORS on the new password.

        Previously only ``min_length=8`` applied on this path, so
        ``12345678`` and ``qwertyui`` were accepted even though
        ``config/settings.py`` configures all four Django validators. The only
        call site for ``validate_password`` anywhere in the project was the
        change-password view, so registration bypassed them entirely.

        An unsaved User is populated with the submitted identity fields first,
        because ``UserAttributeSimilarityValidator`` compares the password
        against them -- without it, "password12345" alongside
        ``email="password12345@x.test"`` would pass.

        The result is keyed to ``password`` so the envelope message stays
        actionable ("password: This password is too common."). This does not
        weaken BR-203: password strength reveals nothing about whether an
        account exists, and the indistinguishable duplicate-email response in
        ``RegisterView`` is untouched.
        """
        password = attrs.get("password")
        if password:
            candidate = User(
                email=attrs.get("email", ""),
                username=attrs.get("username", ""),
                first_name=attrs.get("first_name", ""),
                last_name=attrs.get("last_name", ""),
            )
            try:
                validate_password(password, user=candidate)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({"password": list(exc.messages)})
        return attrs


class LoginSerializer(serializers.Serializer):
    """Accept login via email, matricule, or staffid (at least one required).

    The ``identifier`` field is the flexible login credential.  The frontend
    sends whichever the user typed into the login field.  The view resolves it
    to the matching User account.
    """

    identifier = serializers.CharField(
        required=False,
        allow_blank=True,
        help_text="Email, matricule, or staffid.",
    )
    email = serializers.EmailField(required=False, allow_blank=True)
    matricule = serializers.CharField(required=False, allow_blank=True)
    staffid = serializers.CharField(required=False, allow_blank=True)
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        # Normalise: accept any of the three identifiers or a bare "identifier".
        value = (
            attrs.get("identifier", "").strip()
            or attrs.get("email", "").strip()
            or attrs.get("matricule", "").strip()
            or attrs.get("staffid", "").strip()
        )
        if not value:
            raise serializers.ValidationError(
                "Provide an email, matricule, or staffid to log in."
            )
        attrs["login_identifier"] = value
        return attrs


class UserSerializer(serializers.ModelSerializer):
    """Read/serialise a user.

    SECURITY: this serializer is also used by ``PATCH /accounts/me/``, so
    ``read_only_fields`` is the ONLY thing preventing a self-service caller from
    rewriting its own identity.

    ``matricule`` and ``staffid`` are *login identifiers* (resolved by
    FlexibleLoginBackend), as is ``username``. Before this was tightened, any
    authenticated user could PATCH their own account to claim an arbitrary
    identifier and then authenticate with it; a collision with a real holder
    additionally made the identifier ambiguous at login (BR-001/BR-002/BR-170).

    Self-service is therefore limited to genuinely self-owned profile text.
    Institution-assigned identity is changed by an administrator, roles have
    their own audited endpoint (POST /accounts/change-role/, BR-002/BR-210),
    and email changes require re-verification (BR-209) â€” none of which may be
    reached through here.
    """

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "matricule",
            "staffid",
            "role",
            "faculty",
            "department",
            "level",
            "created_at",
            "is_email_verified",
            "must_change_password",
            "lecturer_approval_status",
        ]
        # Only first_name / last_name are self-writable. Everything else is
        # institution-assigned identity or a security-relevant flag.
        read_only_fields = [
            "id",
            "email",  # changing email requires re-verification (BR-209)
            "username",  # login identifier
            "matricule",  # login identifier (BR-001)
            "staffid",  # login identifier (BR-001)
            "role",  # BR-002/BR-210, admin-only via change-role
            "faculty",
            "department",
            "level",
            "is_email_verified",
            "must_change_password",
            # Authorises acting as teaching staff. Server-owned: an applicant
            # decides only via POST /accounts/lecturers/<id>/approval/ by an
            # administrator. Writable here it would let a PENDING lecturer
            # PATCH their own /accounts/me/ into APPROVED.
            "lecturer_approval_status",
            "created_at",
        ]


class ChangeRoleSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    new_role = serializers.ChoiceField(choices=User.Role.choices)
