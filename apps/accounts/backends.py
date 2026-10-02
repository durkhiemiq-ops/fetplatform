"""Custom authentication backend for flexible login.

Allows users to authenticate with any of:
  - email address
  - matricule number
  - staffid number

Django's ``auth.authenticate()`` passes the credential as ``username``.
This backend resolves that single value against all three identifiers.
"""

from django.contrib.auth.backends import ModelBackend
from django.db.models import Q

from .models import User


def _identifier_query(identifier: str) -> Q:
    """The lookup used for both resolution and ambiguity detection.

    Kept as one function so the "find the match" query and the "is it
    ambiguous?" query can never drift apart.
    """
    return (
        Q(email__iexact=identifier)
        | Q(matricule__iexact=identifier)
        | Q(staffid__iexact=identifier)
    )


class FlexibleLoginBackend(ModelBackend):
    """Authenticate by email, matricule, or staffid."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None

        identifier = username.strip()
        if not identifier:
            return None

        matches = list(
            User.objects.filter(_identifier_query(identifier))[
                :2
            ]
        )

        if not matches:
            # Run the default password hasher to mitigate timing attacks.
            User().set_password(password)
            return None

        if len(matches) > 1:
            # BR-001/BR-170: one active account per identity. An identifier that
            # resolves to more than one account is a data-integrity fault, and
            # FAIL CLOSED. The previous code took `.first()`, which silently
            # authenticated against an arbitrary account — so a case-only
            # collision ("fe24b456" vs "FE24B456" is permitted by the
            # case-sensitive unique constraints) let a login attempt land on
            # whichever row the database happened to return first.
            #
            # Rejecting is correct: no legitimate user should be unable to log
            # in, and picking arbitrarily is a cross-account failure.
            User().set_password(password)
            return None

        user = matches[0]
        if user.check_password(password) and self.user_can_authenticate(user):
            return user

        return None
