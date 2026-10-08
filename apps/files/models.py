import uuid

from django.conf import settings
from django.db import models


def private_upload_path(instance, filename):
    """Generate an opaque storage key; the client filename never becomes a path."""
    suffix = instance.original_name.rsplit(".", 1)[-1].lower()
    return f"private/course-files/{instance.course_offering_id}/{uuid.uuid4().hex}.{suffix}"


class UploadedFile(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_offering = models.ForeignKey(
        "academic.CourseOffering", on_delete=models.PROTECT, related_name="uploaded_files"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="uploaded_files"
    )
    file = models.FileField(upload_to=private_upload_path, max_length=500)
    original_name = models.CharField(max_length=255)
    mime_type = models.CharField(max_length=120)
    size_bytes = models.PositiveBigIntegerField()
    sha256 = models.CharField(max_length=64)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "files_uploaded_file"
        ordering = ["-created_at"]


class LearningMaterial(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ARCHIVED = "ARCHIVED", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    course_offering = models.ForeignKey(
        "academic.CourseOffering", on_delete=models.PROTECT, related_name="materials"
    )
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="learning_materials"
    )
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    file = models.ForeignKey(UploadedFile, on_delete=models.PROTECT, related_name="materials")
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "files_learning_material"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["file"], name="unique_material_file"),
        ]
