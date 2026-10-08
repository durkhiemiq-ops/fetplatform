from rest_framework import serializers

from .models import LearningMaterial, UploadedFile


class RejectUnknownFieldsMixin:
    """DRF otherwise silently discards unexpected client-controlled fields."""

    def to_internal_value(self, data):
        unknown = set(data.keys()) - set(self.fields.keys())
        if unknown:
            names = ", ".join(sorted(str(name) for name in unknown))
            raise serializers.ValidationError({"unknown_fields": f"Unexpected fields: {names}."})
        return super().to_internal_value(data)


class FileUploadSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    file = serializers.FileField()
    course_offering = serializers.UUIDField()


class UploadedFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = UploadedFile
        fields = ["id", "original_name", "mime_type", "size_bytes", "sha256", "created_at"]
        read_only_fields = fields


class MaterialCreateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    title = serializers.CharField(max_length=300, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=10000)
    file = serializers.UUIDField()


class MaterialUpdateSerializer(RejectUnknownFieldsMixin, serializers.Serializer):
    title = serializers.CharField(required=False, max_length=300, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=10000)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one field is required.")
        return attrs


class LearningMaterialSerializer(serializers.ModelSerializer):
    file_info = UploadedFileSerializer(source="file", read_only=True)

    class Meta:
        model = LearningMaterial
        fields = [
            "id", "course_offering", "title", "description", "file_info",
            "created_at", "updated_at",
        ]
        read_only_fields = fields
