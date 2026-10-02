"""Assessment persistence matching the assessment service contract."""

import uuid

from django.db import models


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
    private_notes = models.TextField(blank=True)
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
