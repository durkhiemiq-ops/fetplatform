"""Strict input schemas for the curriculum registration and configuration APIs."""

from rest_framework import serializers

from .models import (
    AcademicTerm, Programme, ProgrammeLevel, Specialization, Curriculum,
    CurriculumCourse, StudentAcademicProfile,
)


class StrictFieldsMixin:
    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Expected an object.")
        writable = {name for name, field in self.fields.items() if not field.read_only}
        unexpected = set(data) - writable
        if unexpected:
            raise serializers.ValidationError({key: "This field is not permitted." for key in sorted(unexpected)})
        return super().to_internal_value(data)


class CurriculumCompletionSerializer(StrictFieldsMixin, serializers.Serializer):
    specialization = serializers.UUIDField(required=False, allow_null=True)


class EmptyInputSerializer(StrictFieldsMixin, serializers.Serializer):
    pass


class SemesterTermSerializer(StrictFieldsMixin, serializers.Serializer):
    academic_term = serializers.PrimaryKeyRelatedField(queryset=AcademicTerm.objects.all())


class ProgrammeSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Programme
        fields = ["id", "department", "code", "name", "is_active"]
        read_only_fields = ["id"]


class ProgrammeLevelSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = ProgrammeLevel
        fields = ["id", "programme", "code", "name", "specialization_required"]
        read_only_fields = ["id"]


class AcademicTermSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = AcademicTerm
        fields = ["id", "code", "name"]
        read_only_fields = ["id"]


class SpecializationSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Specialization
        fields = ["id", "programme", "code", "name", "is_active"]
        read_only_fields = ["id"]


class CurriculumSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = Curriculum
        fields = ["id", "programme", "version", "cohort_from", "cohort_to", "is_published", "published_at"]
        read_only_fields = ["id", "is_published", "published_at"]


class CurriculumCourseSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = CurriculumCourse
        fields = ["id", "curriculum", "programme_level", "academic_term", "course", "specialization", "classification", "is_required"]
        read_only_fields = ["id"]


class StudentAcademicProfileSerializer(StrictFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = StudentAcademicProfile
        fields = ["student", "programme", "programme_level", "cohort", "curriculum", "specialization", "pinned_at"]
        read_only_fields = ["curriculum", "specialization", "pinned_at"]


CONFIG_SERIALIZERS = {
    "programmes": ProgrammeSerializer,
    "levels": ProgrammeLevelSerializer,
    "terms": AcademicTermSerializer,
    "specializations": SpecializationSerializer,
    "curricula": CurriculumSerializer,
    "requirements": CurriculumCourseSerializer,
    "profiles": StudentAcademicProfileSerializer,
}
