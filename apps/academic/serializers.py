from rest_framework import serializers

from .models import ClassSession, Course, CourseOffering, Department, Faculty, SchoolYear, Semester


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
        fields = [
            "id", "code", "name", "description", "credit_units", "level",
            "status", "department", "department_name", "faculty_name",
        ]

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
            "registration_deadline",
            "status",
            "is_current",
        ]

    def validate(self, attrs):
        return _validate_dates(attrs, getattr(self, "instance", None))


class CourseOfferingSerializer(serializers.ModelSerializer):
    course_code = serializers.CharField(source="course.code", read_only=True)
    course_title = serializers.CharField(source="course.name", read_only=True)
    credit_units = serializers.IntegerField(source="course.credit_units", read_only=True)
    course_level = serializers.CharField(source="course.level", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    semester_name = serializers.CharField(source="semester.name", read_only=True)
    lecturer_name = serializers.SerializerMethodField()

    class Meta:
        model = CourseOffering
        fields = [
            "id", "course", "course_code", "course_title", "credit_units",
            "course_level", "semester", "semester_name", "department",
            "department_name", "lecturer", "lecturer_name", "status",
            "registration_deadline", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def get_lecturer_name(self, obj) -> str:
        if obj.lecturer is None:
            return ""
        return f"{obj.lecturer.first_name} {obj.lecturer.last_name}".strip()

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        course = attrs.get("course", getattr(self.instance, "course", None))
        department = attrs.get("department", getattr(self.instance, "department", None))
        lecturer = attrs.get("lecturer", getattr(self.instance, "lecturer", None))
        if course and course.department_id and course.department_id != getattr(department, "id", None):
            raise serializers.ValidationError({"department": "Must match the course department."})
        if lecturer and lecturer.role != "LECTURER":
            raise serializers.ValidationError({"lecturer": "Must identify a lecturer."})
        return attrs


class StudentRegistrationSerializer(serializers.Serializer):
    offering_ids = serializers.ListField(
        child=serializers.UUIDField(), allow_empty=False, max_length=30
    )

    def validate(self, attrs):
        unexpected = set(self.initial_data) - {"offering_ids"}
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        ids = attrs["offering_ids"]
        if len(ids) != len(set(ids)):
            raise serializers.ValidationError({"offering_ids": "Duplicate offerings are not permitted."})
        return attrs


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
