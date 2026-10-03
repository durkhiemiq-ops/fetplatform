from decimal import Decimal

from rest_framework import serializers

from apps.academic.models import ClassSession, Course
from apps.accounts.models import User

from .models import Assessment


class AssessmentSerializer(serializers.ModelSerializer):
    """Output shape; private notes never leave for students (BR-131)."""

    student_name = serializers.SerializerMethodField()
    private_notes = serializers.SerializerMethodField()

    class Meta:
        model = Assessment
        fields = [
            "id",
            "student",
            "student_name",
            "course",
            "class_session",
            "score",
            "status",
            "released",
            "private_notes",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def get_student_name(self, obj) -> str:
        return f"{obj.student.first_name} {obj.student.last_name}".strip()

    def get_private_notes(self, obj):
        if self.context.get("is_academic"):
            return obj.private_notes
        return None


class AssessmentCreateSerializer(serializers.Serializer):
    """Create payload for create_assessment (BR-130 authorization in service)."""

    student = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(role=User.Role.STUDENT)
    )
    score = serializers.DecimalField(
        max_digits=7, decimal_places=2, required=False, allow_null=True, default=None
    )
    private_notes = serializers.CharField(required=False, allow_blank=True, default="")
    released = serializers.BooleanField(default=False, required=False)
    course = serializers.PrimaryKeyRelatedField(
        queryset=Course.objects.all(), required=False, allow_null=True, default=None
    )
    class_session = serializers.PrimaryKeyRelatedField(
        queryset=ClassSession.objects.all(),
        required=False,
        allow_null=True,
        default=None,
    )

    def validate(self, attrs):
        course = attrs.get("course")
        class_session = attrs.get("class_session")
        if course is not None and class_session is not None:
            if class_session.course_id != course.pk:
                raise serializers.ValidationError(
                    "class_session must belong to the selected course."
                )
        return attrs

    def validate_score(self, value):
        if value is not None and value < Decimal("0"):
            raise serializers.ValidationError("Score cannot be negative.")
        return value


class AssessmentUpdateSerializer(serializers.Serializer):
    """Partial edit for update_assessment; every path is audited (BR-132)."""

    score = serializers.DecimalField(
        max_digits=7, decimal_places=2, required=False, allow_null=True
    )
    private_notes = serializers.CharField(required=False, allow_blank=True)
    released = serializers.BooleanField(required=False)

    def validate_score(self, value):
        if value is not None and value < Decimal("0"):
            raise serializers.ValidationError("Score cannot be negative.")
        return value
