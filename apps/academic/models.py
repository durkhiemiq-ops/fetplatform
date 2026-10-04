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

    class Meta:
        db_table = "academic_semester"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school_year", "name"], name="unique_semester_per_year"
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
