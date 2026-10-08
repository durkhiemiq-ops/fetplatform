import uuid

from django.conf import settings
from django.db import models


class AttendanceSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        EXPIRED = "EXPIRED", "Expired"
        CLOSED = "CLOSED", "Closed"

    class Mode(models.TextChoices):
        #: One short-lived QR on the projector/lecturer screen. Every enrolled
        #: student in the room scans it; each scan credits only the scanner.
        PROJECTOR = "PROJECTOR", "Projected code"
        #: Distributed stations: the lecturer seeds eligible students, and every
        #: successful scan auto-activates that student as a station for this
        #: session (seed -> B -> C cascade).
        STATIONS = "STATIONS", "Student stations"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    class_session = models.ForeignKey(
        "academic.ClassSession", on_delete=models.PROTECT, related_name="attendance_sessions"
    )
    lecturer = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_sessions_started"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    mode = models.CharField(max_length=10, choices=Mode.choices, default=Mode.PROJECTOR)
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = "attendance_session"
        indexes = [models.Index(fields=["status", "expires_at"])]


class AttendanceCheckpoint(models.Model):
    """A session-scoped scan point — in STATION mode this row *is* the station.

    There is deliberately one table: a station is not a second, parallel copy of
    a checkpoint. Rows are created either by the lecturer's seed selection
    (``source=SEED``, no attendance implied) or automatically when a student
    scans an active station and is therefore able to relay scans
    (``source=CASCADE``). Authority is session-scoped and dies with the session:
    it is never a role on the user account.
    """

    class Source(models.TextChoices):
        SEED = "SEED", "Lecturer seed"
        CASCADE = "CASCADE", "Activated by a valid scan"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance_session = models.ForeignKey(
        AttendanceSession, on_delete=models.CASCADE, related_name="checkpoints"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_checkpoints"
    )
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.SEED)
    activated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="station_activations",
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attendance_checkpoint"
        constraints = [
            models.UniqueConstraint(
                fields=["attendance_session", "student"], name="unique_checkpoint_per_session_student"
            ),
        ]


class AttendanceRecord(models.Model):
    class Status(models.TextChoices):
        PRESENT = "PRESENT", "Present"
        LATE = "LATE", "Late"
        ABSENT = "ABSENT", "Absent"
        EXCUSED = "EXCUSED", "Excused"

    class VerificationMethod(models.TextChoices):
        QR_SCAN = "QR_SCAN", "QR code scan"
        MANUAL = "MANUAL", "Manual"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    attendance_session = models.ForeignKey(
        AttendanceSession, on_delete=models.PROTECT, related_name="records"
    )
    student = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_records"
    )
    # The scan point the credit came from: a station in STATIONS mode, or None
    # for a projected-code scan, which has no per-student scan point at all.
    # NULL is a real value here, not a fallback — projected sessions never had
    # one, and inventing a placeholder row would fake a station.
    checkpoint = models.ForeignKey(
        AttendanceCheckpoint,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attendance_records",
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PRESENT)
    verification_method = models.CharField(
        max_length=20,
        choices=VerificationMethod.choices,
        default=VerificationMethod.QR_SCAN,
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attendance_record"
        constraints = [
            # BR-040: this database constraint is the concurrency defense.
            models.UniqueConstraint(
                fields=["attendance_session", "student"], name="unique_attendance_per_session_student"
            ),
        ]


class AttendanceCorrection(models.Model):
    """Immutable correction request/event; original attendance is retained."""

    attendance_record = models.ForeignKey(
        AttendanceRecord, on_delete=models.PROTECT, related_name="corrections"
    )
    corrected_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="attendance_corrections"
    )
    old_status = models.CharField(
        max_length=20,
        choices=AttendanceRecord.Status.choices,
        default=AttendanceRecord.Status.PRESENT,
    )
    new_status = models.CharField(
        max_length=20,
        choices=AttendanceRecord.Status.choices,
        default=AttendanceRecord.Status.PRESENT,
    )
    reason = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "attendance_correction"
        ordering = ["created_at"]
