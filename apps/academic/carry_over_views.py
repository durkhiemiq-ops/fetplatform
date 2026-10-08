"""HTTP surface for carry-over applications.

Thin adapter over ``services.carry_over_service`` — no business rules here.
Registered on the flat ``api/v1/`` mount (as well as the legacy ``/academic/``
prefix) because the client addresses ``/carry-over/`` directly.

Access model, stated because it is the security-relevant part:

* ``GET  /carry-over/``            — students get their own rows, staff get the
  whole queue. The scope is decided from the caller's role, never from a
  request parameter.
* ``POST /carry-over/apply/``      — a student applies **for themselves**; the
  target student is taken from the session, so no body field can name another.
* ``POST /carry-over/{id}/review/``— staff only. A student attempting to review
  is rejected by the service before any state changes, and an id outside the
  caller's visibility resolves as not-found rather than confirming existence.

State changes go through the service, which writes BR-210 audit entries.
"""

from django.db.models import Q
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.academic_access import is_admin_user

from .models import CarryOverApplication
from .services import carry_over_service as service


def _success(data, status=200):
    return Response({"success": True, "data": data}, status=status)


def _error(message, code, status=400):
    return Response(
        {"success": False, "error": {"code": code, "message": message}},
        status=status,
    )


class CarryOverListView(APIView):
    """List carry-over applications visible to the caller."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        status_filter = request.query_params.get("status")
        rows = service.list_applications(request.user, status_filter)
        return _success([service.serialize(row) for row in rows])


class CarryOverApplyView(APIView):
    """Submit an application. Always for the signed-in student."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        if getattr(request.user, "role", None) != "STUDENT":
            return _error(
                "Only students may apply for a carry-over.",
                "FORBIDDEN",
                403,
            )

        offering_id = request.data.get("course_offering_id")
        if not offering_id:
            return _error("course_offering_id is required.", "INVALID_DATA")

        reason = str(request.data.get("reason") or "").strip()
        if len(reason) > 2000:
            return _error("Reason must be 2000 characters or fewer.", "INVALID_DATA")

        try:
            payload = service.apply_for_carry_over(
                student=request.user,
                course_offering_id=offering_id,
                reason=reason,
            )
        except service.OfferingNotFoundError as exc:
            # §25: an unknown offering id must not confirm what does exist.
            return _error(str(exc), "NOT_FOUND", 404)
        except service.AlreadyEnrolledError as exc:
            return _error(str(exc), "ALREADY_ENROLLED", 409)
        except service.DuplicateApplicationError as exc:
            return _error(str(exc), "CONFLICT", 409)
        except service.CarryOverError as exc:
            return _error(str(exc), "INVALID_DATA")

        return _success(payload, 201)


class CarryOverReviewView(APIView):
    """Staff decision on one application. Approval enrolls the student."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not (service.is_staff(request.user) or is_admin_user(request.user)):
            return _error(
                "Only administrators and lecturers may review applications.",
                "FORBIDDEN",
                403,
            )

        # An id that does not exist and one that is not visible both land on
        # the same 404 envelope, so this endpoint cannot be used to probe for
        # valid ids (§25).
        application = CarryOverApplication.objects.filter(pk=pk).first()
        if application is None:
            return _error("Application not found.", "NOT_FOUND", 404)

        decision = request.data.get("decision")
        note = str(request.data.get("note") or "").strip()
        if len(note) > 2000:
            return _error("Note must be 2000 characters or fewer.", "INVALID_DATA")

        try:
            payload = service.review_application(
                application=application,
                actor=request.user,
                decision=decision,
                note=note,
            )
        except service.NotStaffError as exc:
            return _error(str(exc), "FORBIDDEN", 403)
        except service.InvalidDecisionError as exc:
            return _error(str(exc), "INVALID_DATA")
        except service.NotReviewableError as exc:
            return _error(str(exc), "CONFLICT", 409)

        return _success(payload)
