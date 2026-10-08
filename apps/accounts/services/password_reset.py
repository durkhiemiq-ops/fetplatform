"""Anonymous password recovery with purpose-separated, single-use OTPs."""

import hashlib
import logging

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.mail import send_mail
from django.db import transaction

from core.audit import write_audit_entry
from ..models import User
from .email_otp import issue_otp, verify_otp, OTPResult, get_otp_ttl_seconds, normalize_email

logger = logging.getLogger(__name__)
PURPOSE = "password_reset"
REQUEST_MESSAGE = "If that address belongs to an active account, a password reset code has been sent."


class ResetCredentialError(ValueError):
    pass


class ResetPasswordPolicyError(ValueError):
    pass


def request_password_reset(*, email):
    email = normalize_email(email)
    # Same bounded issuance budget for known and unknown addresses, across IPs.
    identity_key = hashlib.sha256(email.encode("utf-8")).hexdigest()
    try:
        if not cache.add("account:password-reset-request:" + identity_key, True, timeout=60):
            return
        account = User.objects.filter(email__iexact=email, is_active=True).first()
        if account is None or not account.has_usable_password():
            return
        code = issue_otp(account.email, purpose=PURPOSE + ":" + account.password)
        send_mail(
            "Your FET Platform password reset code",
            f"Your password reset code is: {code}\n\n"
            f"It expires in {max(1, get_otp_ttl_seconds() // 60)} minutes and can be used once.\n"
            "If you did not request this, ignore this email. Your password has not changed.",
            settings.DEFAULT_FROM_EMAIL, [account.email],
        )
    except Exception as exc:
        # No code, address, password, or provider exception text enters logs.
        logger.warning("Password reset delivery unavailable (%s)", type(exc).__name__)


@transaction.atomic
def reset_password(*, email, code, new_password):
    email = normalize_email(email)
    # Lock the account while consuming the credential and committing its change.
    account = User.objects.select_for_update().filter(email__iexact=email, is_active=True).first()
    context = PURPOSE + ":" + (account.password if account is not None else "unknown")
    valid = verify_otp(email, code, purpose=context)
    if valid is not OTPResult.VERIFIED or account is None or not account.has_usable_password():
        raise ResetCredentialError("Reset failed. Request a new code and try again.")
    try:
        validate_password(new_password, user=account)
    except ValidationError as exc:
        # The consumed code cannot later be replayed, including after validation failure.
        raise ResetPasswordPolicyError(" ".join(exc.messages) + " Request a new reset code to try again.") from exc
    account.set_password(new_password)
    account.must_change_password = False
    account.save(update_fields=["password", "must_change_password"])
    write_audit_entry(
        action="password_reset", resource_type="account", resource_id=account.pk,
        actor_id=account.pk, details={"method": "email_otp"},
    )
    # No session is created; existing sessions fail Django's password-hash check.
