from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts.models import User
from core.models import AuditEvent

from .models import (
    ClassSchedule,
    Course,
    CourseOffering,
    Department,
    Enrollment,
    Faculty,
    SchoolYear,
    Semester,
)


class AcademicStructureApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.admin = self.user("structure-admin", User.Role.ADMINISTRATOR)
        self.student = self.user("structure-student", User.Role.STUDENT)
        self.outsider = self.user("structure-outsider", User.Role.STUDENT)
        self.pending = self.user(
            "structure-pending", User.Role.LECTURER, User.LecturerApproval.PENDING
        )
        self.rejected = self.user(
            "structure-rejected", User.Role.LECTURER, User.LecturerApproval.REJECTED
        )
        self.approved = self.user(
            "structure-approved", User.Role.LECTURER, User.LecturerApproval.APPROVED
        )
        self.legacy = self.user("structure-legacy", User.Role.LECTURER)
        self.faculty = Faculty.objects.create(name="Engineering")
        self.department = Department.objects.create(
            name="Computer Science", code="CSC", faculty=self.faculty
        )
        self.course = Course.objects.create(
            code="CSC401", name="Secure Systems",
            department=self.department, level="400"
        )
        self.year = SchoolYear.objects.create(
            name="2030/2031", start_date="2030-09-01", end_date="2031-07-31"
        )
        self.semester = Semester.objects.create(
            school_year=self.year, name="Semester 1",
            start_date="2030-09-01", end_date="2031-01-31", is_current=True
        )
        self.offering = CourseOffering.objects.create(
            course=self.course, semester=self.semester,
            department=self.department, lecturer=self.approved
        )
        Enrollment.objects.create(
            student=self.student, course=self.course,
            course_offering=self.offering, is_active=True
        )

    def user(self, username, role, approval=None):
        return User.objects.create_user(
            f"{username}@example.test", username, "Test", username,
            "StrongPass!2026", role=role, lecturer_approval_status=approval
        )

    def authenticate(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def schedule_payload(self, **changes):
        payload = {
            "class_type": "LECTURE", "day_of_week": "MONDAY",
            "start_time": "08:00", "end_time": "09:00",
            "location": "Room 204",
        }
        payload.update(changes)
        return payload

    def test_public_departments_is_anonymous_and_minimal(self):
        response = self.client.get("/api/v1/departments/public/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["data"], [{
            "id": str(self.department.pk), "name": "Computer Science",
            "code": "CSC", "faculty": "Engineering",
        }])

    def test_department_creation_is_admin_only_strict_and_audited(self):
        url = "/api/v1/departments/create/"
        payload = {
            "name": "Electrical Engineering", "code": "eee",
            "faculty": str(self.faculty.pk),
        }
        denied = self.authenticate(self.student).post(
            url, {**payload, "faculty": "00000000-0000-0000-0000-000000000000"},
            format="json",
        )
        self.assertEqual(denied.status_code, 403)
        unknown = self.authenticate(self.admin).post(
            url, {**payload, "role": "ADMINISTRATOR"}, format="json"
        )
        self.assertEqual(unknown.status_code, 400)
        created = self.client.post(url, payload, format="json")
        self.assertEqual(created.status_code, 201, created.data)
        department = Department.objects.get(code="EEE")
        self.assertTrue(AuditEvent.objects.filter(
            action="department_created", resource_id=str(department.pk),
            actor_id=self.admin.pk
        ).exists())

    def test_canonical_department_collection_accepts_admin_post(self):
        response = self.authenticate(self.admin).post(
            "/api/v1/departments/",
            {
                "name": "Mathematics",
                "code": "MTH",
                "faculty": str(self.faculty.pk),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(Department.objects.filter(code="MTH").exists())

    def test_lecturer_course_access_respects_approval_policy(self):
        url = "/api/v1/lecturers/me/courses/"
        for user in (self.pending, self.rejected):
            self.offering.lecturer = user
            self.offering.save(update_fields=["lecturer"])
            response = self.authenticate(user).get(url)
            self.assertEqual(response.status_code, 403, user.username)
        for user in (self.approved, self.legacy):
            self.offering.lecturer = user
            self.offering.save(update_fields=["lecturer"])
            response = self.authenticate(user).get(url)
            self.assertEqual(response.status_code, 200, user.username)
            self.assertEqual(len(response.data["data"]), 1)

    def test_offering_requires_an_approved_lecturer_role(self):
        url = f"/api/v1/course-offerings/{self.offering.pk}/"
        for invalid_user in (self.pending, self.rejected, self.admin):
            response = self.authenticate(self.admin).patch(
                url, {"lecturer": str(invalid_user.pk)}, format="json"
            )
            self.assertEqual(response.status_code, 400, invalid_user.username)
        self.offering.refresh_from_db()
        self.assertEqual(self.offering.lecturer_id, self.approved.pk)

    def test_schedule_is_scoped_validated_and_audited(self):
        url = f"/api/v1/course-offerings/{self.offering.pk}/schedules/"
        created = self.authenticate(self.approved).post(
            url, self.schedule_payload(), format="json"
        )
        self.assertEqual(created.status_code, 201, created.data)
        schedule_id = created.data["data"]["id"]
        self.assertTrue(AuditEvent.objects.filter(
            action="class_schedule_created", resource_id=str(schedule_id),
            actor_id=self.approved.pk
        ).exists())
        student_read = self.authenticate(self.student).get(url)
        self.assertEqual(student_read.status_code, 200)
        self.assertEqual(len(student_read.data["data"]), 1)
        student_write = self.client.post(
            url, self.schedule_payload(day_of_week="TUESDAY"), format="json"
        )
        self.assertEqual(student_write.status_code, 403)
        outsider_read = self.authenticate(self.outsider).get(url)
        self.assertEqual(outsider_read.status_code, 404)
        invalid = self.authenticate(self.approved).post(
            url, self.schedule_payload(
                day_of_week="WEDNESDAY", start_time="10:00", end_time="09:00"
            ), format="json"
        )
        self.assertEqual(invalid.status_code, 400)
        overlap = self.client.post(
            url, self.schedule_payload(start_time="08:30", end_time="09:30"),
            format="json"
        )
        self.assertEqual(overlap.status_code, 409)
        deleted = self.client.delete(
            f"/api/v1/schedules/{schedule_id}/"
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertFalse(ClassSchedule.objects.get(pk=schedule_id).is_active)
        self.assertTrue(AuditEvent.objects.filter(
            action="class_schedule_archived", resource_id=str(schedule_id),
            actor_id=self.approved.pk
        ).exists())

    def test_pending_lecturer_cannot_access_directly_assigned_schedule(self):
        self.offering.lecturer = self.pending
        self.offering.save(update_fields=["lecturer"])
        url = f"/api/v1/course-offerings/{self.offering.pk}/schedules/"
        response = self.authenticate(self.pending).post(
            url, self.schedule_payload(), format="json"
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ClassSchedule.objects.exists())

    def test_admin_statistics_excludes_unapproved_applicants(self):
        response = self.authenticate(self.admin).get("/api/v1/admin/stats/")
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["total_students"], 2)
        self.assertEqual(data["total_lecturers"], 2)
        self.assertEqual(data["total_departments"], 1)
        self.assertEqual(data["total_courses"], 1)
        self.assertEqual(data["total_offerings"], 1)
        self.assertEqual(data["total_enrollments"], 1)
        self.assertEqual(data["active_semester"]["name"], "Semester 1")
