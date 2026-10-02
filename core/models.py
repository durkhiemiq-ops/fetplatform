import uuid

from django.db import models


class AuditEvent(models.Model):
    """Append-only audit persistence for security-sensitive platform actions."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=255)
    actor_id = models.CharField(max_length=255)
    details = models.JSONField(default=dict)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    correlation_id = models.CharField(max_length=512, null=True, blank=True)
    timestamp = models.DateTimeField()

    class Meta:
        db_table = "core_audit_event"
        ordering = ["timestamp"]
        indexes = [models.Index(fields=["resource_type", "resource_id", "timestamp"])]
