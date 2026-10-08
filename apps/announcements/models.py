"""Announcement persistence matching the announcement service contract.

The service addresses the class FK as ``class_id`` (``class`` is a Python
keyword), so a property bridges the contract name to the real column.
"""

import uuid

from django.db import models

#: Upper bound on an announcement body, in characters. Declared here once and
#: imported by the serializers, so the model and the API cannot drift into
#: disagreeing about what is acceptable.
BODY_MAX_LENGTH = 10000


class Announcement(models.Model):
    class Scope(models.TextChoices):
        FACULTY = "faculty", "Faculty"
        DEPARTMENT = "department", "Department"
        COURSE = "course", "Course"
        CLASS = "class", "Class"
        COURSE_CLASS = "course_class", "Course + class"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    # Bounded rather than free TEXT: the content model here is plain text plus
    # output encoding (see the XSS gate in scripts/security_audit_checks.py),
    # and an unbounded body is a storage-amplification vector on an endpoint
    # any member of the scope can post to.
    body = models.TextField(max_length=BODY_MAX_LENGTH)
    scope = models.CharField(max_length=32, choices=Scope.choices)
    faculty = models.ForeignKey(
        "academic.Faculty", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    department = models.ForeignKey(
        "academic.Department", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    course = models.ForeignKey(
        "academic.Course", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    class_session = models.ForeignKey(
        "academic.ClassSession", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    is_published = models.BooleanField(default=False)
    is_important = models.BooleanField(default=False)
    is_pinned = models.BooleanField(default=False, db_index=True)
    is_archived = models.BooleanField(default=False, db_index=True)
    created_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    published_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    updated_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "announcements_announcement"
        ordering = ["-created_at"]

    def __str__(self):
        return self.title

    @property
    def class_id(self):
        return self.class_session_id

    @class_id.setter
    def class_id(self, value):
        self.class_session_id = value


class AnnouncementRead(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="reads"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="announcement_reads"
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "announcements_announcement_read"
        ordering = ["-read_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "user"], name="unique_announcement_read"
            )
        ]
