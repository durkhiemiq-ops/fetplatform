from rest_framework import serializers

from .models import AttendanceSession

#: Which QR contract a session honours. Stored server-side at start; a client
#: can request a mode but can never change it afterwards.
MODE_CHOICES = [choice for choice, _ in AttendanceSession.Mode.choices]


class AttendanceScanSerializer(serializers.Serializer):
    # Deliberately no student_id field: identity is request.user only (BR-039/063).
    token = serializers.CharField(trim_whitespace=True, max_length=512)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"token"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        return attrs


class AttendanceSessionCreateSerializer(serializers.Serializer):
    class_session = serializers.UUIDField()
    # BR-036: default duration comes from settings; the lecturer may pick a
    # window inside the service-enforced band (10-600 seconds).
    duration_seconds = serializers.IntegerField(min_value=10, max_value=600, required=False)
    mode = serializers.ChoiceField(choices=MODE_CHOICES, required=False)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"class_session", "duration_seconds", "mode"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        return attrs


class CheckpointSelectSerializer(serializers.Serializer):
    student_ids = serializers.ListField(
        child=serializers.UUIDField(), min_length=1, max_length=200, allow_empty=False
    )

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"student_ids"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        if len(set(attrs["student_ids"])) != len(attrs["student_ids"]):
            raise serializers.ValidationError({"student_ids": "Student ids must be unique."})
        return attrs


class CorrectionCreateSerializer(serializers.Serializer):
    # BR-042: a correction is only meaningful with its audit reason; the
    # original attendance record is never overwritten, only appended to.
    status = serializers.ChoiceField(
        choices=["PRESENT", "LATE", "ABSENT", "EXCUSED"]
    )
    reason = serializers.CharField(trim_whitespace=True, allow_blank=False, max_length=2000)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"status", "reason"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        return attrs


class FlexibleAttendanceStartSerializer(serializers.Serializer):
    offering_id = serializers.UUIDField()
    duration_seconds = serializers.IntegerField(min_value=10, max_value=600, required=False)
    mode = serializers.ChoiceField(choices=MODE_CHOICES, required=False)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"offering_id", "duration_seconds", "mode"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        return attrs


class AutoSelectStationsSerializer(serializers.Serializer):
    """How many eligible students to seed when the lecturer does not pick."""

    count = serializers.IntegerField(min_value=1, max_value=20, required=False, default=3)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"count"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        return attrs
