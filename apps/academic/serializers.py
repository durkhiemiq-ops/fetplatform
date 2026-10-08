from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from core.academic_access import is_authorized_academic_user

from .models import (
    ClassSchedule,
    ClassSession,
    Course,
    CourseOffering,
    Department,
    Faculty,
    SchoolYear,
    Semester,
)


class RejectUnknownWriteFieldsMixin:
    """Reject unknown and read-only request fields instead of silently dropping them."""

    def to_internal_value(self, data):
        writable = {name for name, field in self.fields.items() if not field.read_only}
        unexpected = set(data) - writable
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        return super().to_internal_value(data)


class FacultySerializer(serializers.ModelSerializer):
    class Meta:
        model = Faculty
        fields = ["id", "name"]


class DepartmentSerializer(serializers.ModelSerializer):
    faculty_name = serializers.SerializerMethodField()

    class Meta:
        model = Department
        fields = ["id", "code", "name", "faculty", "faculty_name"]

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
        fields = [
            "id",
            "course",
            "course_offering",
            "course_code",
            "lecturer",
            "lecturer_name",
            "starts_at",
        ]

    def get_lecturer_name(self, obj) -> str:
        return f"{obj.lecturer.first_name} {obj.lecturer.last_name}".strip()


def _validate_dates(attrs, instance=None) -> dict:
    start = attrs.get("start_date", instance.start_date if instance else None)
    end = attrs.get("end_date", instance.end_date if instance else None)
    if start and end and end <= start:
        raise serializers.ValidationError({"end_date": "end_date must be after start_date."})
    return attrs


class SchoolYearSerializer(RejectUnknownWriteFieldsMixin, serializers.ModelSerializer):
    class Meta:
        model = SchoolYear
        fields = ["id", "name", "start_date", "end_date"]

    def validate(self, attrs):
        return _validate_dates(attrs, getattr(self, "instance", None))


class SemesterSerializer(RejectUnknownWriteFieldsMixin, serializers.ModelSerializer):
    school_year_name = serializers.CharField(source="school_year.name", read_only=True)
    # Activation is a controlled transition; the database uniqueness validator
    # would reject the request before the service can displace the old semester.
    is_current = serializers.BooleanField(required=False, default=False)

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
        validators = [
            UniqueTogetherValidator(
                queryset=Semester.objects.all(),
                fields=["school_year", "name"],
            )
        ]

    def validate(self, attrs):
        return _validate_dates(attrs, getattr(self, "instance", None))


class CourseOfferingSerializer(RejectUnknownWriteFieldsMixin, serializers.ModelSerializer):
    course_code = serializers.CharField(source="course.code", read_only=True)
    course_title = serializers.CharField(source="course.name", read_only=True)
    credit_units = serializers.IntegerField(source="course.credit_units", read_only=True)
    course_level = serializers.CharField(source="course.level", read_only=True)
    department_name = serializers.CharField(source="department.name", read_only=True)
    semester_name = serializers.CharField(source="semester.name", read_only=True)
    lecturer_name = serializers.SerializerMethodField()
    # Wire alias for ``id``. Offering-keyed consumers (`/assessment`,
    # the lecturer dashboard, the classroom workspace) address an offering as
    # ``offering_id`` everywhere else in the API, and ``GET /lecturers/me/courses/``
    # answered with ``id`` alone — so those screens read ``undefined`` and
    # navigated to ``/lessons/undefined``. Both names are emitted on purpose;
    # `academic.student_course_views` already does the same.
    offering_id = serializers.UUIDField(source="id", read_only=True)

    class Meta:
        model = CourseOffering
        fields = [
            "id", "offering_id", "course", "course_code", "course_title", "credit_units",
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
        if lecturer and (
            lecturer.role != "LECTURER"
            or not is_authorized_academic_user(lecturer)
        ):
            raise serializers.ValidationError(
                {"lecturer": "Must identify an approved lecturer."}
            )
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


class DepartmentCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    code = serializers.CharField(max_length=30)
    faculty = serializers.PrimaryKeyRelatedField(queryset=Faculty.objects.all())

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        attrs["name"] = attrs["name"].strip()
        attrs["code"] = attrs["code"].strip().upper()
        if not attrs["name"] or not attrs["code"]:
            raise serializers.ValidationError(
                {"code": "Name and code must not be blank."}
            )
        return attrs


class ClassScheduleCreateSerializer(serializers.Serializer):
    class_type = serializers.ChoiceField(choices=ClassSchedule.ClassType.choices)
    day_of_week = serializers.ChoiceField(choices=ClassSchedule.Day.choices)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    location = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )

    def validate(self, attrs):
        unexpected = set(self.initial_data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError(
                {field: "This field is not permitted." for field in unexpected}
            )
        if attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError(
                {"end_time": "end_time must be after start_time."}
            )
        attrs["location"] = attrs.get("location", "").strip()
        return attrs


class ClassDefinitionCreateSerializer(RejectUnknownWriteFieldsMixin, serializers.Serializer):
    """Payload for ``POST /course-offerings/{id}/classes/`` (API §22).

    The documented example carries ``name``, ``class_type``, ``location`` and a
    ``recurrence_rule``. ``name`` is required; ``class_type`` and ``location``
    ride the established schema; the weekly slot triple is accepted only when
    it is needed. ``recurrence_rule`` is **not** a field here — the project
    decision is to keep the existing schedule columns rather than add a
    recurrence parser, so the client is told the key is not permitted instead
    of having it silently dropped.

    Everything that identifies ownership is read from the URL and the session,
    never from the body: an injected ``lecturer``, ``owner``, ``course_offering``
    or role is rejected by the mixin above.
    """

    name = serializers.CharField(max_length=255)
    class_type = serializers.ChoiceField(
        choices=ClassSchedule.ClassType.choices,
        required=False,
        default=ClassSchedule.ClassType.LECTURE,
    )
    location = serializers.CharField(
        max_length=255, required=False, allow_blank=True, default=""
    )
    day_of_week = serializers.ChoiceField(
        choices=ClassSchedule.Day.choices, required=False, allow_null=True
    )
    start_time = serializers.TimeField(required=False, allow_null=True)
    end_time = serializers.TimeField(required=False, allow_null=True)

    def validate(self, attrs):
        slot = {key: attrs.get(key) for key in ("day_of_week", "start_time", "end_time")}
        given = [key for key, value in slot.items() if value is not None]
        if given and len(given) != len(slot):
            raise serializers.ValidationError(
                {
                    "day_of_week": (
                        "day_of_week, start_time and end_time must be supplied together."
                    )
                }
            )
        if len(given) == len(slot) and attrs["end_time"] <= attrs["start_time"]:
            raise serializers.ValidationError(
                {"end_time": "end_time must be after start_time."}
            )
        attrs["name"] = (attrs.get("name") or "").strip()
        if not attrs["name"]:
            raise serializers.ValidationError({"name": "name must not be blank."})
        attrs["location"] = (attrs.get("location") or "").strip()
        for key in ("day_of_week", "start_time", "end_time"):
            attrs.setdefault(key, None)
        return attrs


class ClassDefinitionSerializer(serializers.ModelSerializer):
    """Read shape for one class definition.

    ``status`` is a read-only projection of the existing ``is_active`` column
    rather than a second stored state, so a client can never write it.
    """

    course_code = serializers.CharField(
        source="course_offering.course.code", read_only=True
    )
    course_title = serializers.CharField(
        source="course_offering.course.name", read_only=True
    )
    lecturer_name = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = ClassSchedule
        fields = [
            "id",
            "course_offering",
            "course_code",
            "course_title",
            "name",
            "class_type",
            "location",
            "day_of_week",
            "start_time",
            "end_time",
            "lecturer",
            "lecturer_name",
            "is_active",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_lecturer_name(self, obj):
        return f"{obj.lecturer.first_name} {obj.lecturer.last_name}".strip()

    def get_status(self, obj):
        return "ACTIVE" if obj.is_active else "INACTIVE"


class ClassScheduleSerializer(serializers.ModelSerializer):
    course_code = serializers.CharField(
        source="course_offering.course.code", read_only=True
    )
    course_title = serializers.CharField(
        source="course_offering.course.name", read_only=True
    )
    lecturer_name = serializers.SerializerMethodField()

    class Meta:
        model = ClassSchedule
        fields = [
            "id",
            "course_offering",
            "course_code",
            "course_title",
            "name",
            "lecturer",
            "lecturer_name",
            "class_type",
            "day_of_week",
            "start_time",
            "end_time",
            "location",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_lecturer_name(self, obj):
        return f"{obj.lecturer.first_name} {obj.lecturer.last_name}".strip()
