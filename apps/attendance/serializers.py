from rest_framework import serializers


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

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"class_session", "duration_seconds"}
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
    reason = serializers.CharField(trim_whitespace=True, allow_blank=False, max_length=2000)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"reason"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        return attrs
