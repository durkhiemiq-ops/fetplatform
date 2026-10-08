from rest_framework import serializers

from .models import Announcement, BODY_MAX_LENGTH
from .services.announcement_service import announcement_audience, can_manage_announcement


class AnnouncementSerializer(serializers.ModelSerializer):
    """Output shape for the visible-announcements feed."""

    scope_label = serializers.SerializerMethodField()
    creator_name = serializers.SerializerMethodField()
    audience_label = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()
    read_count = serializers.SerializerMethodField()
    recipient_count = serializers.SerializerMethodField()
    readers = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

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
            "is_pinned",
            "published_at",
            "created_by",
            "creator_name",
            "audience_label",
            "is_read",
            "read_count",
            "recipient_count",
            "readers",
            "can_manage",
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

    def get_audience_label(self, obj) -> str:
        return self.get_scope_label(obj)

    def get_creator_name(self, obj) -> str:
        if obj.created_by is None:
            return "Former user"
        return f"{obj.created_by.first_name} {obj.created_by.last_name}".strip() or obj.created_by.email

    def get_is_read(self, obj) -> bool:
        user = self.context.get("request").user if self.context.get("request") else None
        return bool(user and obj.reads.filter(user=user).exists())

    def get_read_count(self, obj) -> int:
        return obj.reads.count()

    def get_recipient_count(self, obj) -> int:
        return announcement_audience(obj).count()

    def get_readers(self, obj) -> list:
        user = self.context.get("request").user if self.context.get("request") else None
        if not can_manage_announcement(user, obj):
            return []
        return [
            {
                "id": str(row.user_id),
                "full_name": f"{row.user.first_name} {row.user.last_name}".strip(),
                "read_at": row.read_at,
            }
            for row in obj.reads.select_related("user")[:4]
        ]

    def get_can_manage(self, obj) -> bool:
        user = self.context.get("request").user if self.context.get("request") else None
        return can_manage_announcement(user, obj)


class AnnouncementCreateSerializer(serializers.Serializer):
    """Create payload; the service performs the authorization decision (BR-083)."""

    title = serializers.CharField(max_length=255)
    body = serializers.CharField(max_length=BODY_MAX_LENGTH)
    scope = serializers.ChoiceField(
        choices=[c.value for c in Announcement.Scope if c.value != "course_class"]
    )
    scope_id = serializers.UUIDField()
    is_important = serializers.BooleanField(default=False, required=False)
    published = serializers.BooleanField(default=False, required=False)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        return attrs


class AnnouncementUpdateSerializer(serializers.Serializer):
    """Partial edit payload for update_announcement (BR-084 audits publishes)."""

    title = serializers.CharField(max_length=255, required=False)
    body = serializers.CharField(required=False, max_length=BODY_MAX_LENGTH)
    is_important = serializers.BooleanField(required=False)
    published = serializers.BooleanField(required=False)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        if not attrs:
            raise serializers.ValidationError("At least one field is required.")
        return attrs

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Announcement title cannot be empty.")
        return value

    def validate_body(self, value):
        if not value.strip():
            raise serializers.ValidationError("Announcement body cannot be empty.")
        return value
