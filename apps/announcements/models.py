"""Announcement persistence matching the announcement service contract.

The service addresses the class FK as ``class_id`` (``class`` is a Python
keyword), so a property bridges the contract name to the real column.
"""

import uuid

from django.db import models


class Announcement(models.Model):
    class Scope(models.TextChoices):
        FACULTY = "faculty", "Faculty"
        DEPARTMENT = "department", "Department"
        COURSE = "course", "Course"
        CLASS = "class", "Class"
        COURSE_CLASS = "course_class", "Course + class"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    body = models.TextField()
    scope = models.CharField(max_length=32, choices=Scope.choices)
    faculty = models.ForeignKey(
        "academic.Faculty", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    department = models.ForeignKey(
        "academic.Department", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    course = models.ForeignKey(
        "academic.Course", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    class_session = models.ForeignKey(
        "academic.ClassSession", on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    is_published = models.BooleanField(default=False)
    is_important = models.BooleanField(default=False)
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
