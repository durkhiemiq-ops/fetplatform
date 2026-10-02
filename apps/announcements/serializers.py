from rest_framework import serializers

from apps.academic.models import ClassSession, Course, Department, Faculty

from .models import Announcement


class AnnouncementSerializer(serializers.ModelSerializer):
    """Output shape for the visible-announcements feed."""

    scope_label = serializers.SerializerMethodField()

    class Meta:
        model = Announcement
        fields = [
            "id",
            "title",
            "body",
            "scope",
            "scope_label",
            "faculty",
            "department",
            "course",
            "class_session",
            "is_published",
            "is_important",
            "published_at",
            "created_by",
            "created_at",
        ]

    def get_scope_label(self, obj) -> str:
        if obj.scope == "faculty" and obj.faculty_id:
            return obj.faculty.name
        if obj.scope == "department" and obj.department_id:
            return obj.department.name
        if obj.scope == "course" and obj.course_id:
            return str(obj.course)
        if obj.scope in {"class", "course_class"} and obj.class_session_id:
            return f"{obj.class_session.course.code} class"
        return obj.scope


class AnnouncementCreateSerializer(serializers.Serializer):
    """Create payload; the service performs the authorization decision (BR-083)."""

    title = serializers.CharField(max_length=255)
    body = serializers.CharField()
    scope = serializers.ChoiceField(
        choices=[c.value for c in Announcement.Scope if c.value != "course_class"]
    )
    scope_id = serializers.UUIDField()
    is_important = serializers.BooleanField(default=False, required=False)
    published = serializers.BooleanField(default=False, required=False)

    def validate(self, attrs):
        scope_models = {
            "faculty": Faculty,
            "department": Department,
            "course": Course,
            "class": ClassSession,
        }
        model = scope_models.get(attrs["scope"])
        if model is None:
            raise serializers.ValidationError({"scope": "Unsupported announcement scope."})
        if not model.objects.filter(pk=attrs["scope_id"]).exists():
            raise serializers.ValidationError(
                {"scope_id": "No target exists for this scope."}
            )
        return attrs


class AnnouncementUpdateSerializer(serializers.Serializer):
    """Partial edit payload for update_announcement (BR-084 audits publishes)."""

    title = serializers.CharField(max_length=255, required=False)
    body = serializers.CharField(required=False)
    is_important = serializers.BooleanField(required=False)
    published = serializers.BooleanField(required=False)

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Announcement title cannot be empty.")
        return value

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError("Announcement body cannot be empty.")
        return value
