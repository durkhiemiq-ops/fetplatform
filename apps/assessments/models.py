"""Assessment persistence matching the assessment service contract.

Two generations of model live in this module, deliberately:

* :class:`Assessment` — the original per-student result record. It is the
  "minimal released-results journey" the integration map converged on, and it
  is untouched by what follows. The DB design forbids disturbing historical
  academic records, so nothing here repurposes, renames, or drops it.

* The coursework surface (:class:`Assignment` through
  :class:`AssessmentGroup`) — an **inferred** schema. No business rule, API
  contract, or database table in the specification set defines coursework
  assignments, submissions, marks, or assessment groups; the only
  mark-shaped tables the DB design proposes are project-scoped
  ``assessment_components`` / ``assessment_records``. This surface therefore
  implements the client contract as observed in ``frontend/src/lib/learning.js``
  and the components that consume it. Every field below is an inference from
  that client, not a quotation from a spec, and is labelled as such so a later
  specification revision can replace it deliberately rather than have to
  discover it implicitly.

The coursework tables are additive: they reference the offering and its
enrolled students, and never write to or reinterpret ``Assessment`` rows.
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

#: Upper bound on a lecturer's ``private_notes``, in characters. Private notes
#: are plain text under output encoding (see the XSS gate in
#: scripts/security_audit_checks.py); the bound is defensive rather than a
#: product rule, and is shared with the assessment serializers.
PRIVATE_NOTES_MAX_LENGTH = 10000


class Assessment(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        OFFICIAL = "official", "Official"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="assessments"
    )
    course = models.ForeignKey(
        "academic.Course", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    class_session = models.ForeignKey(
        "academic.ClassSession", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    score = models.DecimalField(max_digits=7, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT)
    released = models.BooleanField(default=False)
    private_notes = models.TextField(blank=True, max_length=PRIVATE_NOTES_MAX_LENGTH)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        db_table = "assessments_assessment"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Assessment {self.pk}"

    @property
    def class_id(self):
        return self.class_session_id

    @class_id.setter
    def class_id(self, value):
        self.class_session_id = value


# --------------------------------------------------------------------------
# Coursework surface (inferred from the client; see module docstring).
# --------------------------------------------------------------------------


class Assignment(models.Model):
    """A piece of coursework a student submits against an offering.

    Inferred from ``CourseDetail.jsx``: ``title``, ``due_at``,
    ``allow_late``, ``max_submissions``, ``description``, and an optional
    brief file. ``status`` gates whether students may turn work in
    (``asgn.status === 'ACTIVE'``).
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        CLOSED = "CLOSED", "Closed"
        ARCHIVED = "ARCHIVED", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_offering = models.ForeignKey(
        "academic.CourseOffering",
        on_delete=models.PROTECT,
        related_name="assignments",
    )
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    due_at = models.DateTimeField(null=True, blank=True)
    allow_late = models.BooleanField(default=False)
    max_submissions = models.PositiveSmallIntegerField(default=1)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    attachment = models.ForeignKey(
        "files.UploadedFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignments",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assignments_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assessments_assignment"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.course_offering_id})"

    @property
    def is_past_due(self):
        return self.due_at is not None and self.due_at < timezone.now()


class Submission(models.Model):
    """One student's attempt at an assignment.

    Inferred from ``CourseDetail.jsx``: ``note``, an optional ``file`` FK to
    the shared uploader, a ``grade`` and ``feedback`` the lecturer fills in,
    and a ``status`` of SUBMITTED / GRADED / RETURNED that the client switches
    on. A RETURNED submission is one the student may turn in again.
    """

    class Status(models.TextChoices):
        SUBMITTED = "SUBMITTED", "Submitted"
        GRADED = "GRADED", "Graded"
        RETURNED = "RETURNED", "Returned"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assignment = models.ForeignKey(
        Assignment, on_delete=models.PROTECT, related_name="submissions"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assignment_submissions",
    )
    note = models.TextField(blank=True, default="")
    file = models.ForeignKey(
        "files.UploadedFile",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignment_submissions",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.SUBMITTED, db_index=True
    )
    grade = models.CharField(max_length=40, blank=True, default="")
    feedback = models.TextField(blank=True, default="")
    submitted_at = models.DateTimeField(auto_now_add=True)
    graded_at = models.DateTimeField(null=True, blank=True)
    graded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assignment_submissions_graded",
    )

    class Meta:
        db_table = "assessments_submission"
        ordering = ["-submitted_at"]
        # Deliberately no unique constraint on (assignment, student): the cap
        # on attempts is per-assignment (``max_submissions``), not a one-row
        # rule, so it cannot be expressed as a uniqueness constraint. It is
        # enforced in the service, which can read the assignment's own limit
        # and allow a resubmission after a RETURNED attempt.

    def __str__(self):
        return f"{self.assignment_id}:{self.student_id}:{self.status}"


class AssessmentMark(models.Model):
    """A lecturer's mark against a CA/exam sheet for one student.

    Inferred from ``AssessmentPanel.jsx``: the sheet carries ``title``,
    ``category`` (CA or EXAM), ``maximum_score``, ``weight``, and
    ``status`` DRAFT/PUBLISHED; each student row carries ``score``,
    ``reported_score``, ``comment``, and a ``dispute_status`` of
    OPEN/RESOLVED with a reason and response.
    """

    class DisputeStatus(models.TextChoices):
        OPEN = "OPEN", "Open"
        RESOLVED = "RESOLVED", "Resolved"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    assessment = models.ForeignKey(
        "AssessmentSheet", on_delete=models.PROTECT, related_name="marks"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assessment_marks",
    )
    score = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True
    )
    comment = models.TextField(blank=True, default="")
    dispute_status = models.CharField(
        max_length=16,
        choices=DisputeStatus.choices,
        default=DisputeStatus.RESOLVED,
        db_index=True,
    )
    dispute_reason = models.TextField(blank=True, default="")
    dispute_response = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assessment_marks_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assessments_mark"
        ordering = ["student__last_name", "student__first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["assessment", "student"],
                name="unique_mark_per_assessment_student",
            )
        ]

    def __str__(self):
        return f"{self.assessment_id}:{self.student_id}:{self.score}"


class AssessmentSheet(models.Model):
    """A CA or exam sheet an offering's marks are entered against.

    Inferred from ``AssessmentPanel.jsx``. Distinct from the original
    ``Assessment`` model, which records an already-released per-student
    result; this one is the lecturer's working sheet, published to release
    the marks it holds.
    """

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Draft"
        PUBLISHED = "PUBLISHED", "Published"

    class Category(models.TextChoices):
        CA = "CA", "Continuous assessment"
        EXAM = "EXAM", "Exam"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_offering = models.ForeignKey(
        "academic.CourseOffering",
        on_delete=models.PROTECT,
        related_name="assessment_sheets",
    )
    title = models.CharField(max_length=255)
    category = models.CharField(
        max_length=16, choices=Category.choices, default=Category.CA
    )
    maximum_score = models.DecimalField(max_digits=7, decimal_places=2, default=100)
    weight = models.DecimalField(
        max_digits=5, decimal_places=2, default=100, help_text="Percentage of the course grade."
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DRAFT, db_index=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assessment_sheets_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assessments_sheet"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.course_offering_id})"


class AssessmentGroup(models.Model):
    """Several sheets rolled up into one reported grade.

    Inferred from ``AssessmentPanel.jsx``: ``getGroups``/``createGroup`` hang
    off the offering, and a group holds the sheets whose scores sum into one
    reported figure (e.g. one CA out of 30).
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_offering = models.ForeignKey(
        "academic.CourseOffering",
        on_delete=models.PROTECT,
        related_name="assessment_groups",
    )
    title = models.CharField(max_length=255)
    sheets = models.ManyToManyField(
        AssessmentSheet, related_name="groups", blank=True
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assessment_groups_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "assessments_group"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} ({self.course_offering_id})"
