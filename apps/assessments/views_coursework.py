"""Coursework HTTP surface.

Thin adapter over :mod:`apps.assessments.services.coursework_service`: every
method resolves the route, hands the request to the service, and maps domain
errors onto the project's error envelope. No business rule is decided here.

Route shapes follow the client exactly (``frontend/src/lib/learning.js``):

* ``GET  /course-offerings/<id>/assignments/``          list assignments
* ``POST /course-offerings/<id>/assignments/``          create one
* ``PUT  /assignments/<id>/``                           edit (client sends PUT)
* ``DELETE /assignments/<id>/``                         remove
* ``GET  /assignments/<id>/submissions/``               list submissions
* ``POST /assignments/<id>/submissions/``               student turns work in
* ``PATCH /submissions/<id>/``                          lecturer grades/returns
* ``GET  /course-offerings/<id>/assessment-sheets/``    list sheets
* ``POST /course-offerings/<id>/assessment-sheets/``    create one
* ``PUT  /assessment-sheets/<id>/``                     edit
* ``DELETE /assessment-sheets/<id>/``                   remove
* ``PUT  /assessment-sheets/<id>/marks/``               save marks
* ``PATCH /assessment-marks/<id>/``                     edit one mark / dispute
* ``GET  /course-offerings/<id>/assessment-groups/``    list groups
* ``POST /course-offerings/<id>/assessment-groups/``    create one
* ``PATCH /assessment-groups/<id>/``                    edit
* ``DELETE /assessment-groups/<id>/``                   remove
* ``GET  /assignments/`` and ``GET/POST /students/me/assignments/``          the student's own coursework view

The service decides who may act; the permission classes here only establish
that the caller is signed in and, for writes, is teaching staff. Ownership of
a specific offering is checked per object in the service, so a lecturer
reaching for another lecturer's offering receives the same denial as one
reaching for nothing at all.
"""

import uuid

from django.http import HttpResponse
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsApprovedAcademicUser

from .models import Assessment, Assignment, AssessmentSheet
from .services import coursework_service as service
from .views import AssessmentUpdateView


def _success(data, status=200):
    return Response({"success": True, "data": data}, status=status)


def _error(message, code, status=400):
    return Response(
        {"success": False, "error": {"code": code, "message": message}},
        status=status,
    )


def _handle(view_self, request, fn, *args, **kwargs):
    """Run a service callable, mapping its domain errors to the envelope."""
    try:
        return fn(*args, **kwargs)
    except (
        service.OfferingNotFoundError,
        service.AssignmentNotFoundError,
        service.SubmissionNotFoundError,
        service.SheetNotFoundError,
        service.GroupNotFoundError,
    ) as exc:
        return _error(str(exc), "NOT_FOUND", 404)
    except service.OfferingAccessDenied:
        # Only raised before any object row has been resolved — an offering the
        # caller may not write to. At that level "forbidden" and "missing" are
        # the same question about the same object, so both must answer
        # identically: a caller cannot tell an offering they do not own from
        # one that was never created (§25). Denials *after* an object row has
        # been fetched raise that object's own not-found error instead, so the
        # two never diverge.
        return _error("That course offering does not exist.", "NOT_FOUND", 404)
    except service.SubmissionLimitError as exc:
        return _error(str(exc), "SUBMISSION_LIMIT", 409)
    except service.MarkEditForbidden as exc:
        # The object is visible to this caller (a student disputing their own
        # released mark), so §25 does not apply and this is a genuine 403.
        return _error(str(exc), "FORBIDDEN", 403)
    except service.ExportForbidden as exc:
        # Same reasoning: the sheet is already readable by this caller, the
        # export is simply a staff-only action on it.
        return _error(str(exc), "FORBIDDEN", 403)
    except service.EmptyGroupError as exc:
        # Its own code, ahead of the generic branches: the client is told the
        # collection holds nothing to release rather than a bare invalid input,
        # and the caller can disable the button instead of guessing.
        return _error(str(exc), "EMPTY_GROUP", 400)
    except service.InvalidInputError as exc:
        return _error(str(exc), "INVALID_INPUT", 400)
    except service.CourseworkError as exc:
        return _error(str(exc), "INVALID_INPUT", 400)


# ---------------------------------------------------------------------------
# Assignments
# ---------------------------------------------------------------------------


class OfferingAssignmentListCreateView(APIView):
    """``GET``/``POST`` on one offering's assignments."""

    permission_classes = [IsAuthenticated, IsApprovedAcademicUser]

    def get_permissions(self):
        # Reading coursework is open to enrolled students as well as staff,
        # so the stricter class only applies to the create half.
        if self.request.method == "POST":
            return [IsAuthenticated(), IsApprovedAcademicUser()]
        return [IsAuthenticated()]

    def get(self, request, offering_id):
        return _handle(
            self,
            request,
            lambda: _success(
                service.list_assignments(user=request.user, offering_id=offering_id)
            ),
        )

    def post(self, request, offering_id):
        data = request.data if hasattr(request, "data") else {}
        return _handle(
            self,
            request,
            lambda: _success(
                service.create_assignment(
                    user=request.user,
                    offering_id=offering_id,
                    title=data.get("title", ""),
                    description=data.get("description", ""),
                    due_at=data.get("due_at"),
                    allow_late=data.get("allow_late", False),
                    max_submissions=data.get("max_submissions", 1),
                    attachment=data.get("attachment"),
                ),
                201,
            ),
        )


class AssignmentDetailView(APIView):
    """Edit or delete one assignment."""

    permission_classes = [IsAuthenticated, IsApprovedAcademicUser]

    def put(self, request, pk):
        fields = {
            key: request.data.get(key)
            for key in ("title", "description", "due_at", "allow_late", "status")
            if key in request.data
        }
        return _handle(
            self,
            request,
            lambda: _success(
                service.update_assignment(user=request.user, assignment_id=pk, **fields)
            ),
        )

    def patch(self, request, pk):
        # The client sends PUT, but PATCH is accepted as well so that either
        # verb resolves to the same service call rather than a hard 404.
        return self.put(request, pk)

    def delete(self, request, pk):
        return _handle(
            self,
            request,
            lambda: _success(service.delete_assignment(user=request.user, assignment_id=pk)),
        )


class AssignmentSubmissionListCreateView(APIView):
    """``GET`` submissions for staff; ``POST`` a student's own submission."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return _handle(
            self,
            request,
            lambda: _success(
                service.list_submissions(user=request.user, assignment_id=pk)
            ),
        )

    def post(self, request, pk):
        data = request.data if hasattr(request, "data") else {}
        return _handle(
            self,
            request,
            lambda: _success(
                service.submit_work(
                    user=request.user,
                    assignment_id=pk,
                    note=data.get("note", ""),
                    file=data.get("file"),
                ),
                201,
            ),
        )


class SubmissionDetailView(APIView):
    """A lecturer grades, returns, or comments on one submission."""

    permission_classes = [IsAuthenticated, IsApprovedAcademicUser]

    def patch(self, request, pk):
        data = request.data if hasattr(request, "data") else {}
        fields = {
            key: data.get(key)
            for key in ("grade", "feedback", "status")
            if key in data
        }
        return _handle(
            self,
            request,
            lambda: _success(
                service.grade_submission(user=request.user, submission_id=pk, **fields)
            ),
        )

    def put(self, request, pk):
        return self.patch(request, pk)


# ---------------------------------------------------------------------------
# Assessment sheets and marks
# ---------------------------------------------------------------------------


class OfferingSheetListCreateView(APIView):
    """``GET``/``POST`` on one offering's assessment sheets."""

    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method == "POST":
            return [IsAuthenticated(), IsApprovedAcademicUser()]
        return [IsAuthenticated()]

    def get(self, request, offering_id):
        return _handle(
            self,
            request,
            lambda: _success(
                service.list_sheets(user=request.user, offering_id=offering_id)
            ),
        )

    def post(self, request, offering_id):
        data = request.data if hasattr(request, "data") else {}
        # Mirror the group-PATCH rule: a field the sheet model does not have is
        # an error the caller can see, never a value that vanishes. The create
        # form used to post `description`, `raw_maximum` and `attachment`, all
        # of which were accepted and then thrown away.
        allowed = {"title", "category", "maximum_score", "weight"}
        unexpected = sorted(set(data) - allowed)

        def run():
            if unexpected:
                raise service.InvalidInputError(
                    "Unsupported field(s): {}. Sheet create supports title, "
                    "category, maximum_score and weight.".format(", ".join(unexpected))
                )
            return _success(
                service.create_sheet(
                    user=request.user,
                    offering_id=offering_id,
                    title=data.get("title", ""),
                    category=data.get("category", "CA"),
                    maximum_score=data.get("maximum_score", 100),
                    weight=data.get("weight", 100),
                ),
                201,
            )

        return _handle(self, request, run)


class SheetDetailView(APIView):
    """Read, edit or delete one assessment sheet."""

    permission_classes = [IsAuthenticated, IsApprovedAcademicUser]

    def get_permissions(self):
        # Reading a sheet is open to enrolled students as well as staff (the
        # service decides who may see *which* sheet), so the approval gate
        # only applies to the write half.
        if self.request.method == "GET":
            return [IsAuthenticated()]
        return [IsAuthenticated(), IsApprovedAcademicUser()]

    def get(self, request, pk):
        return _handle(
            self,
            request,
            lambda: _success(service.get_sheet(user=request.user, sheet_id=pk)),
        )

    def patch(self, request, pk):
        # No service call before _handle: an unknown or foreign sheet id must
        # reach the same error mapping as any other, not raise out of the view
        # and come back as a bare 500.
        fields = {
            key: request.data.get(key)
            for key in ("title", "category", "maximum_score", "weight")
            if key in request.data
        }
        return _handle(
            self,
            request,
            lambda: _success(
                service.update_sheet(
                    user=request.user, sheet_id=pk, **fields
                )
            ),
        )

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        return _handle(
            self,
            request,
            lambda: _success(service.delete_sheet(user=request.user, sheet_id=pk)),
        )


class SheetMarksView(APIView):
    """``PUT`` replaces a sheet's marks; ``GET`` lists them."""

    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        if self.request.method in ("PUT", "POST"):
            return [IsAuthenticated(), IsApprovedAcademicUser()]
        return [IsAuthenticated()]

    def get(self, request, pk):
        return _handle(
            self,
            request,
            lambda: _success(service.list_marks(user=request.user, sheet_id=pk)),
        )

    def put(self, request, pk):
        marks = request.data.get("marks", []) if hasattr(request, "data") else []
        return _handle(
            self,
            request,
            lambda: _success(
                service.save_marks(user=request.user, sheet_id=pk, marks=marks)
            ),
        )

    def post(self, request, pk):
        return self.put(request, pk)


class AssessmentMarkDetailView(APIView):
    """Edit one mark, or raise/resolve a dispute about it.

    Open to any signed-in user rather than gated to teaching staff: a student
    must be able to reach this route to raise a dispute about their own mark
    (``raiseDispute`` on the results page). Who may change *what* is decided
    in the service, where the distinction between "dispute your own mark" and
    "grade somebody's mark" belongs — a permission class here could only make
    the whole route staff-only, which would strand the student dispute flow.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        data = request.data if hasattr(request, "data") else {}
        fields = {
            key: data.get(key)
            for key in ("score", "comment", "dispute_reason", "dispute_response")
            if key in data
        }
        return _handle(
            self,
            request,
            lambda: _success(
                service.update_mark(user=request.user, mark_id=pk, **fields)
            ),
        )

    def put(self, request, pk):
        return self.patch(request, pk)


class AssessmentMarkPublishView(APIView):
    """``PATCH`` a sheet between DRAFT and PUBLISHED."""

    permission_classes = [IsAuthenticated, IsApprovedAcademicUser]

    def patch(self, request, pk):
        status = request.data.get("status", "") if hasattr(request, "data") else ""
        return _handle(
            self,
            request,
            lambda: _success(
                service.publish_sheet(user=request.user, sheet_id=pk, status=status)
            ),
        )


# ---------------------------------------------------------------------------
# Groups
# ---------------------------------------------------------------------------


class OfferingGroupListCreateView(APIView):
    """``GET``/``POST`` on one offering's assessment groups."""

    permission_classes = [IsAuthenticated, IsApprovedAcademicUser]

    def get(self, request, offering_id):
        return _handle(
            self,
            request,
            lambda: _success(
                service.list_groups(user=request.user, offering_id=offering_id)
            ),
        )

    def post(self, request, offering_id):
        data = request.data if hasattr(request, "data") else {}
        return _handle(
            self,
            request,
            lambda: _success(
                service.create_group(
                    user=request.user,
                    offering_id=offering_id,
                    title=data.get("title", ""),
                    sheets=data.get("sheets"),
                ),
                201,
            ),
        )


class GroupDetailView(APIView):
    """Read, edit or delete one assessment group."""

    permission_classes = [IsAuthenticated, IsApprovedAcademicUser]

    def get(self, request, pk):
        # The service answers 404 to every caller who may not see the group,
        # so this stays on the strict staff permission class without hiding a
        # real row behind a 403.
        return _handle(
            self,
            request,
            lambda: _success(service.get_group(user=request.user, group_id=pk)),
        )

    def patch(self, request, pk):
        # The raw body, unfiltered: anything that is not `title` or `sheets`
        # is named back by the service instead of being silently dropped. The
        # retired `{status: ...}` body in particular must be refused outright —
        # a collection holds no publication state of its own — so a client
        # still sending it finds out rather than believing it worked.
        data = request.data if hasattr(request, "data") else {}
        if not isinstance(data, dict):
            return _error("Expected a JSON object body.", "INVALID_INPUT", 400)
        return _handle(
            self,
            request,
            lambda: _success(
                service.update_group(
                    user=request.user, group_id=pk, fields=dict(data)
                )
            ),
        )

    def put(self, request, pk):
        return self.patch(request, pk)

    def delete(self, request, pk):
        return _handle(
            self,
            request,
            lambda: _success(service.delete_group(user=request.user, group_id=pk)),
        )


class GroupPublishView(APIView):
    """``POST /assessment-groups/{id}/publish/`` — release a whole collection.

    Accepted project decision B: the body is `{}` and deliberately carries no
    state, so a caller cannot dictate a target status or any other transition.
    Everything about *what* is released is derived server-side from the
    collection's own membership and the canonical per-sheet rules.
    """

    permission_classes = [IsAuthenticated, IsApprovedAcademicUser]

    def post(self, request, pk):
        data = request.data if hasattr(request, "data") else {}
        if not isinstance(data, dict) or data:
            return _error(
                "This operation takes an empty body ({}). Publication state is "
                "derived server-side and cannot be supplied by the client.",
                "INVALID_INPUT",
                400,
            )
        return _handle(
            self,
            request,
            lambda: _success(
                service.publish_group(user=request.user, group_id=pk), 200
            ),
        )


# ---------------------------------------------------------------------------
# The student's own coursework view
# ---------------------------------------------------------------------------


class MyAssignmentsView(APIView):
    """``GET /students/me/assignments/`` — everything this student must hand in.

    Returns the student's assignments with their own submission folded into
    ``my_submission``, so the page needs no second call and no other student's
    work is ever fetched.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if getattr(user, "role", None) != "STUDENT":
            return _error(
                "This endpoint returns a student's own coursework.",
                "FORBIDDEN",
                403,
            )
        return _success(service.list_my_assignments(user=user))


# ---------------------------------------------------------------------------
# CSV export
# ---------------------------------------------------------------------------


def _csv_file_response(payload):
    """Send the rendered CSV as a file download.

    A download cannot answer with the JSON envelope on *success*: the client
    reads the body bytes directly and takes the filename from
    ``Content-Disposition`` (``downloadBlob`` in ``frontend/src/lib/learning.js``).
    Every failure still travels through ``_handle``, so errors on this route
    arrive as the standard error envelope like everywhere else.
    """
    response = HttpResponse(payload["content"], content_type=payload["content_type"])
    response["Content-Disposition"] = f'attachment; filename="{payload["filename"]}"'
    return response


class SheetExportView(APIView):
    """``GET`` one assessment sheet's marks as a CSV file.

    Both the canonical ``/assessment-sheets/<id>/export.csv`` and the client's
    ``/assessments/<id>/export.csv`` land here, so there is one definition of
    what an export contains and who may take one.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return _handle(
            self,
            request,
            lambda: _csv_file_response(
                service.export_sheet_marks_csv(user=request.user, sheet_id=pk)
            ),
        )


class GroupExportView(APIView):
    """``GET`` every sheet in one assessment group as a CSV file."""

    permission_classes = [IsAuthenticated, IsApprovedAcademicUser]

    def get(self, request, pk):
        return _handle(
            self,
            request,
            lambda: _csv_file_response(
                service.export_group_marks_csv(user=request.user, group_id=pk)
            ),
        )


# ---------------------------------------------------------------------------
# Compatibility dispatch
# ---------------------------------------------------------------------------


class AssessmentPathAliasView(APIView):
    """Resolve the client's ``/assessments/<id>/`` paths onto their owners.

    The client names coursework sheets under ``/assessments/<id>/`` while the
    canonical sheet routes live under ``/assessment-sheets/<id>/``, and the
    released-results endpoint (BR-131) is mounted on the very same prefix by
    ``apps.assessments.urls``. Moving either surface would break clients that
    already work, so instead this view resolves the id and hands the request
    to the view that already owns it — the canonical one — which means the
    behaviour, permissions and business rules stay in a single place and are
    never re-implemented here.

    Ownership is decided by **which table holds the row**, never by the id's
    shape: a well-formed UUID proves nothing about where it lives. An id that
    no table holds falls through to the sheet view, whose service answers the
    same not-found envelope a real-but-unseen sheet produces, so a probe
    cannot tell an absent id from one the caller may not see.
    """

    permission_classes = [IsAuthenticated]

    # Released results are PATCH-only. Routing every other verb there would
    # answer 405 for an id that exists and 404 for one that does not, which
    # distinguishes the two; those verbs are sent to the sheet view instead so
    # both cases return the identical not-found envelope (§25).
    _RELEASED_VERBS = ("PATCH",)

    @staticmethod
    def _target_view(pk):
        """The view that owns ``pk``, or ``None`` when no table holds it."""
        try:
            key = uuid.UUID(str(pk))
        except (ValueError, TypeError, AttributeError):
            return None
        # Order is deliberate: the only ids the client sends down this path
        # are sheet ids, so a sheet is claimed first.
        if AssessmentSheet.objects.filter(pk=key).exists():
            return SheetDetailView
        if Assessment.objects.filter(pk=key).exists():
            return AssessmentUpdateView
        return None

    def _route(self, request, pk):
        target = self._target_view(pk)
        if target is None or (
            target is AssessmentUpdateView
            and request.method not in self._RELEASED_VERBS
        ):
            target = SheetDetailView
        # Delegate through the target's own ``as_view`` so the request is
        # dispatched with *that* view's permissions, throttles and handlers: a
        # student may read a published sheet through here and may not touch
        # released results, exactly as if they had called the canonical route.
        # The underlying HttpRequest is passed because wrapping an already
        # wrapped request would re-run authentication against DRF's own
        # wrapper instead of the real one.
        return target.as_view()(request._request, pk=pk)

    def get(self, request, pk):
        return self._route(request, pk)

    def put(self, request, pk):
        return self._route(request, pk)

    def patch(self, request, pk):
        return self._route(request, pk)

    def delete(self, request, pk):
        return self._route(request, pk)
