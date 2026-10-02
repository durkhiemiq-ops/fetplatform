from rest_framework import serializers

from .models import ClassSession, Course, Department, Faculty, SchoolYear, Semester


class FacultySerializer(serializers.ModelSerializer):
    class Meta:
        model = Faculty
        fields = ["id", "name"]


class DepartmentSerializer(serializers.ModelSerializer):
    faculty_name = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ["id", "name", "faculty", "faculty_name"]

    def get_faculty_name(self, obj) -> str | None:
        return obj.faculty.name if obj.faculty else None


class CourseSerializer(serializers.ModelSerializer):
    """Course with display names resolved so the catalogue needs one request."""

    department_name = serializers.SerializerMethodField()
    faculty_name = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ["id", "code", "name", "department", "department_name", "faculty_name"]

    def get_department_name(self, obj) -> str | None:
        return obj.department.name if obj.department else None

    def get_faculty_name(self, obj) -> str | None:
        if obj.department and obj.department.faculty:
            return obj.department.faculty.name
        return None


class ClassSessionSerializer(serializers.ModelSerializer):
    """Taught class occurrences — feeds announcement scope pickers and lists."""

    course_code = serializers.CharField(source="course.code", read_only=True)
    lecturer_name = serializers.SerializerMethodField()

    class Meta:
        model = ClassSession
        fields = ["id", "course", "course_code", "lecturer", "lecturer_name", "starts_at"]

    def get_lecturer_name(self, obj) -> str:
        return f"{obj.lecturer.first_name} {obj.lecturer.last_name}".strip()


def _validate_dates(attrs, instance=None) -> dict:
    start = attrs.get("start_date", instance.start_date if instance else None)
    end = attrs.get("end_date", instance.end_date if instance else None)
    if start and end and end <= start:
        raise serializers.ValidationError({"end_date": "end_date must be after start_date."})
    return attrs


class SchoolYearSerializer(serializers.ModelSerializer):
    class Meta:
        model = SchoolYear
        fields = ["id", "name", "start_date", "end_date"]

    def validate(self, attrs):
        return _validate_dates(attrs, getattr(self, "instance", None))


class SemesterSerializer(serializers.ModelSerializer):
    school_year_name = serializers.CharField(source="school_year.name", read_only=True)

    class Meta:
        model = Semester
        fields = [
            "id",
            "school_year",
            "school_year_name",
            "name",
            "start_date",
            "end_date",
            "is_current",
        ]

    def validate(self, attrs):
        return _validate_dates(attrs, getattr(self, "instance", None))


class EnrollmentCreateSerializer(serializers.Serializer):
    """Enroll the caller (or, for an administrator, another student).

    ``student`` is optional and is only honoured for administrators; a student
    may only ever create their own enrollment (BR-010/BR-011).
    """

    course = serializers.UUIDField()
    student = serializers.UUIDField(required=False, allow_null=True)

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"course", "student"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        if not Course.objects.filter(pk=attrs["course"]).exists():
            raise serializers.ValidationError({"course": "Course does not exist."})
        return attrs
