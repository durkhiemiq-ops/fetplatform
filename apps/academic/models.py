import uuid

from django.db import models
from django.utils import timezone


class Faculty(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    class Meta:
        db_table = "academic_faculty"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Department(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True, null=True, blank=True)
    name = models.CharField(max_length=255)
    faculty = models.ForeignKey(
        Faculty,
        on_delete=models.CASCADE,
        related_name="departments",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "academic_department"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Course(models.Model):
    """Minimal course aggregate used for enrollment-derived eligibility."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    credit_units = models.PositiveSmallIntegerField(default=3)
    level = models.CharField(max_length=10, blank=True, default="")
    status = models.CharField(max_length=20, default="ACTIVE", db_index=True)
    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="courses",
        null=True,
        blank=True,
    )

    class Meta:
        db_table = "academic_course"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} — {self.name}"


class ClassSession(models.Model):
    """A taught occurrence of a course; attendance sessions attach here."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="class_sessions")
    course_offering = models.ForeignKey(
        "CourseOffering",
        on_delete=models.PROTECT,
        related_name="class_sessions",
        null=True,
        blank=True,
        help_text="Offering-specific source of truth; null only for legacy sessions.",
    )
    lecturer = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="class_sessions"
    )
    starts_at = models.DateTimeField()

    class Meta:
        db_table = "academic_class_session"
        ordering = ["-starts_at"]


class Enrollment(models.Model):
    """Course enrollment is the sole source of attendance eligibility."""

    student = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="enrollments")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="enrollments")
    course_offering = models.ForeignKey(
        "CourseOffering",
        on_delete=models.PROTECT,
        related_name="enrollments",
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    status = models.CharField(max_length=20, default="active")
    enrolled_at = models.DateTimeField(default=timezone.now)
    dropped_at = models.DateTimeField(null=True, blank=True)
    enrolled_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="enrollments_created",
        null=True,
        blank=True,
    )
    dropped_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="enrollments_dropped",
        null=True,
        blank=True,
    )
    reason = models.TextField(blank=True, default="")
    deleted_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)
    source = models.CharField(
        max_length=20, default="LEGACY", choices=[("LEGACY", "Legacy/manual"), ("CURRICULUM", "Curriculum")]
    )
    curriculum_requirement = models.ForeignKey(
        "CurriculumCourse", on_delete=models.PROTECT, null=True, blank=True,
        related_name="generated_enrollments",
    )

    class Meta:
        db_table = "academic_enrollment"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course"],
                condition=models.Q(course_offering__isnull=True),
                name="unique_legacy_course_enrollment",
            ),
            models.UniqueConstraint(
                fields=["student", "course_offering"],
                condition=models.Q(course_offering__isnull=False),
                name="unique_offering_enrollment",
            ),
        ]


class SchoolYear(models.Model):
    """Academic year container (e.g. "2025/2026")."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=30, unique=True)
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        db_table = "academic_school_year"
        ordering = ["-start_date"]

    def __str__(self):
        return self.name


class Semester(models.Model):
    """A term inside a school year; at most one is current platform-wide."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    school_year = models.ForeignKey(
        SchoolYear, on_delete=models.CASCADE, related_name="semesters"
    )
    name = models.CharField(max_length=60)
    start_date = models.DateField()
    end_date = models.DateField()
    registration_deadline = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=20, default="ACTIVE")
    is_current = models.BooleanField(default=False)
    academic_term = models.ForeignKey(
        "AcademicTerm", on_delete=models.PROTECT, null=True, blank=True,
        related_name="semesters",
    )

    class Meta:
        db_table = "academic_semester"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_year", "name"], name="unique_semester_per_year"
            ),
            models.UniqueConstraint(
                fields=["is_current"],
                condition=models.Q(is_current=True),
                name="single_current_semester",
            ),
        ]

    def __str__(self):
        return f"{self.school_year.name} — {self.name}"

    def save(self, *args, **kwargs):
        # Only one semester may claim "current" at a time.
        if self.is_current:
            Semester.objects.filter(is_current=True).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)


class CourseOffering(models.Model):
    """A course delivered by a lecturer during one semester."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="offerings")
    semester = models.ForeignKey(
        Semester, on_delete=models.PROTECT, related_name="course_offerings"
    )
    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="course_offerings"
    )
    lecturer = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="course_offerings",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=20, default="ACTIVE", db_index=True)
    registration_deadline = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "academic_course_offering"
        ordering = ["course__code"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "semester"], name="unique_course_offering_per_semester"
            ),
        ]

    def __str__(self):
        return f"{self.course.code} — {self.semester.name}"


class ClassSchedule(models.Model):
    """A class definition for one course offering.

    This is the repository's **class definition** (Database Design §19/§21,
    API Specification §22): a teaching context attached to a course offering
    that carries its type, location and — optionally — its weekly slot. The
    internal name is narrower than the documented concept; see
    ``docs/mvp-integration-context.md`` for the mapping note rather than a
    broad rename.

    The weekly slot columns are optional because a class definition exists
    before it is scheduled: ``POST /course-offerings/{id}/classes/`` accepts a
    name alone, while ``POST /course-offerings/{id}/schedules/`` still requires
    a full slot. An individual *session* of a class is a different entity
    (``ClassSession``) and is never created here.
    """

    class ClassType(models.TextChoices):
        LECTURE = "LECTURE", "Lecture"
        LAB = "LAB", "Lab"
        TUTORIAL = "TUTORIAL", "Tutorial"
        SEMINAR = "SEMINAR", "Seminar"
        WORKSHOP = "WORKSHOP", "Workshop"
        OTHER = "OTHER", "Other"

    class Day(models.TextChoices):
        MONDAY = "MONDAY", "Monday"
        TUESDAY = "TUESDAY", "Tuesday"
        WEDNESDAY = "WEDNESDAY", "Wednesday"
        THURSDAY = "THURSDAY", "Thursday"
        FRIDAY = "FRIDAY", "Friday"
        SATURDAY = "SATURDAY", "Saturday"
        SUNDAY = "SUNDAY", "Sunday"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_offering = models.ForeignKey(
        CourseOffering, on_delete=models.PROTECT, related_name="schedules"
    )
    lecturer = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="class_schedules"
    )
    name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Documented class name (API §22). Required on class creation.",
    )
    class_type = models.CharField(
        max_length=20, choices=ClassType.choices, default=ClassType.LECTURE
    )
    day_of_week = models.CharField(max_length=10, choices=Day.choices, null=True, blank=True)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    location = models.CharField(max_length=255, blank=True, default="")
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "academic_class_schedule"
        ordering = ["day_of_week", "start_time"]
        constraints = [
            models.UniqueConstraint(
                fields=["course_offering", "day_of_week", "start_time"],
                condition=models.Q(is_active=True),
                name="unique_active_offering_schedule_start",
            ),
            models.CheckConstraint(
                condition=models.Q(end_time__gt=models.F("start_time")),
                name="schedule_end_after_start",
            ),
        ]

    def __str__(self):
        if self.day_of_week is None or self.start_time is None:
            # An unscheduled class definition still has a name; formatting a
            # null time would raise instead of describing the row.
            return f"{self.course_offering} - {self.name or self.class_type}"
        return (
            f"{self.course_offering} - {self.day_of_week} "
            f"{self.start_time:%H:%M}"
        )


class AcademicTerm(models.Model):
    """Reusable curriculum term, explicitly assigned to dated semesters."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)


class Programme(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programmes")
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)


class ProgrammeLevel(models.Model):
    """Codes match institution-assigned User.level; branching is configured."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="levels")
    code = models.CharField(max_length=10)
    name = models.CharField(max_length=100)
    specialization_required = models.BooleanField(default=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["programme", "code"], name="unique_programme_level")]


class Specialization(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="specializations")
    code = models.CharField(max_length=30)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["programme", "code"], name="unique_programme_specialization")]


class Curriculum(models.Model):
    """Published versions are frozen; cohort is the institution-owned entry year."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="curricula")
    version = models.PositiveIntegerField()
    cohort_from = models.PositiveSmallIntegerField()
    cohort_to = models.PositiveSmallIntegerField()
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["programme", "version"], name="unique_programme_curriculum_version"),
            models.CheckConstraint(condition=models.Q(cohort_to__gte=models.F("cohort_from")), name="curriculum_cohort_range_valid"),
        ]


class CurriculumCourse(models.Model):
    class Classification(models.TextChoices):
        PROGRAMME_CORE = "PROGRAMME_CORE", "Programme core"
        SPECIALIZATION_CORE = "SPECIALIZATION_CORE", "Specialization core"
        ELECTIVE = "ELECTIVE", "Elective"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    curriculum = models.ForeignKey(Curriculum, on_delete=models.PROTECT, related_name="requirements")
    programme_level = models.ForeignKey(ProgrammeLevel, on_delete=models.PROTECT, related_name="requirements")
    academic_term = models.ForeignKey(AcademicTerm, on_delete=models.PROTECT, related_name="requirements")
    course = models.ForeignKey(Course, on_delete=models.PROTECT, related_name="curriculum_requirements")
    specialization = models.ForeignKey(Specialization, on_delete=models.PROTECT, null=True, blank=True, related_name="requirements")
    classification = models.CharField(max_length=30, choices=Classification.choices)
    is_required = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=~models.Q(classification="ELECTIVE", is_required=True), name="electives_are_optional"),
            models.CheckConstraint(
                condition=(
                    models.Q(classification="PROGRAMME_CORE", specialization__isnull=True)
                    | models.Q(classification="SPECIALIZATION_CORE", specialization__isnull=False)
                    | models.Q(classification="ELECTIVE")
                ), name="curriculum_classification_scope_valid",
            ),
            models.UniqueConstraint(
                fields=["curriculum", "programme_level", "academic_term", "course"],
                condition=models.Q(specialization__isnull=True), name="unique_common_curriculum_course",
            ),
            models.UniqueConstraint(
                fields=["curriculum", "programme_level", "academic_term", "course", "specialization"],
                condition=models.Q(specialization__isnull=False), name="unique_specialized_curriculum_course",
            ),
        ]


class StudentAcademicProfile(models.Model):
    student = models.OneToOneField("accounts.User", primary_key=True, on_delete=models.PROTECT, related_name="academic_profile")
    programme = models.ForeignKey(Programme, on_delete=models.PROTECT, related_name="student_profiles")
    programme_level = models.ForeignKey(ProgrammeLevel, on_delete=models.PROTECT, related_name="student_profiles")
    cohort = models.PositiveSmallIntegerField()
    curriculum = models.ForeignKey(Curriculum, on_delete=models.PROTECT, null=True, blank=True, related_name="student_profiles")
    specialization = models.ForeignKey(Specialization, on_delete=models.PROTECT, null=True, blank=True, related_name="student_profiles")
    pinned_at = models.DateTimeField(null=True, blank=True)


class CurriculumRegistration(models.Model):
    """Historical snapshot; later registration cannot rewrite it."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    profile = models.ForeignKey(StudentAcademicProfile, on_delete=models.PROTECT, related_name="registrations")
    semester = models.ForeignKey(Semester, on_delete=models.PROTECT, related_name="curriculum_registrations")
    programme_level = models.ForeignKey(ProgrammeLevel, on_delete=models.PROTECT)
    curriculum = models.ForeignKey(Curriculum, on_delete=models.PROTECT)
    specialization = models.ForeignKey(Specialization, on_delete=models.PROTECT, null=True, blank=True)
    offering_ids = models.JSONField(default=list)
    summary = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["profile", "semester"], name="unique_student_semester_curriculum")]


class CarryOverApplication(models.Model):
    """A student's request to join an offering they are not enrolled in.

    Frontend surface: the Carry-over page (`/carry-over`). The student submits
    an application against one offering; a member of staff reviews it, and
    *approval* is what actually creates the Enrollment (the page states this to
    the reviewer, because attendance eligibility — BR-030/BR-031 — follows from
    enrollment and nothing else).

    Statuses are uppercase because that is the value the client compares
    against (`PENDING` / `APPROVED` / `REJECTED`).
    """

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    student = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="carry_over_applications",
    )
    course_offering = models.ForeignKey(
        CourseOffering,
        on_delete=models.PROTECT,
        related_name="carry_over_applications",
    )
    reason = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    review_note = models.TextField(blank=True, default="")
    reviewed_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="carry_over_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "academic_carry_over_application"
        ordering = ["-created_at"]
        constraints = [
            # One live application per student per offering: repeated clicks
            # must not queue up duplicate requests, and the DB — not a
            # read-then-write check — is what enforces it.
            models.UniqueConstraint(
                fields=["student", "course_offering"],
                condition=models.Q(status="PENDING"),
                name="unique_pending_carry_over_per_offering",
            )
        ]

    def __str__(self):
        return f"{self.student_id} -> {self.course_offering_id} ({self.status})"
