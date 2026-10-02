"""API tests for scoped announcements (BR-080 to BR-084)."""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import Course, Department, Enrollment, Faculty
from core.models import AuditEvent

from .models import Announcement


class AnnouncementApiTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.faculty = Faculty.objects.create(name="Engineering")
        self.other_faculty = Faculty.objects.create(name="Sciences")
        self.department = Department.objects.create(
            name="Computer Science", faculty=self.faculty
        )
        self.course = Course.objects.create(
            code="FET101", name="Secure Attendance", department=self.department
        )
        other_department = Department.objects.create(
            name="Physics", faculty=self.other_faculty
        )
        self.other_course = Course.objects.create(
            code="FET102", name="Other Course", department=other_department
        )

        self.lecturer = User.objects.create_user(
            "lecturer@example.test",
            "lecturer",
            "Lect",
            "Urer",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.lecturer.faculty = self.faculty
        self.lecturer.save()
        self.foreign_lecturer = User.objects.create_user(
            "foreign@example.test",
            "foreign",
            "For",
            "Eigner",
            "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.foreign_lecturer.faculty = self.other_faculty
        self.foreign_lecturer.save()
        self.student = User.objects.create_user(
            "student@example.test", "student", "Stu", "Dent", "StrongPass!2026"
        )
        self.student.faculty = self.faculty
        self.student.department = self.department
        self.student.save()
        Enrollment.objects.create(student=self.student, course=self.course)

        Announcement.objects.create(
            title="Your course", body="b", scope="course", course=self.course,
            is_published=True,
        )
        Announcement.objects.create(
            title="Other course", body="b", scope="course", course=self.other_course,
            is_published=True,
        )
        Announcement.objects.create(
            title="Faculty news", body="b", scope="faculty", faculty=self.faculty,
            is_published=True,
        )
        Announcement.objects.create(
            title="Draft", body="b", scope="course", course=self.course,
            is_published=False,
        )

    def test_requires_authentication(self):
        response = self.client.get(reverse("announcements:list"))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_student_feed_is_scoped_to_visible_published(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("announcements:list"))
        self.assertEqual(response.status_code, 200)
        titles = {row["title"] for row in response.data["data"]}
        # BR-082: other-course scopes never leak; drafts never publish.
        self.assertEqual(titles, {"Your course", "Faculty news"})

    def test_students_cannot_create(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(
            reverse("announcements:list"),
            {
                "title": "Hi",
                "body": "b",
                "scope": "course",
                "scope_id": str(self.course.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_lecturer_creates_published_announcement_for_own_scope(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("announcements:list"),
            {
                "title": "Lab moved",
                "body": "Room 12",
                "scope": "faculty",
                "scope_id": str(self.faculty.id),
                "published": True,
                "is_important": True,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.data["data"]["is_published"])
        row = Announcement.objects.get(title="Lab moved")
        self.assertEqual(row.created_by, self.lecturer)
        self.assertIsNotNone(row.published_at)

    def test_lecturer_rejected_for_foreign_scope(self):
        self.client.force_authenticate(user=self.foreign_lecturer)
        response = self.client.post(
            reverse("announcements:list"),
            {
                "title": "Nope",
                "body": "b",
                "scope": "faculty",
                "scope_id": str(self.faculty.id),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "UNAUTHORIZED")

    def test_unknown_scope_target_rejected(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("announcements:list"),
            {
                "title": "Ghost",
                "body": "b",
                "scope": "course",
                "scope_id": "11111111-1111-1111-1111-111111111111",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    def test_published_edit_writes_audit_event(self):
        self.client.force_authenticate(user=self.lecturer)
        target = Announcement.objects.get(title="Faculty news")
        response = self.client.patch(
            reverse("announcements:detail", args=[target.pk]),
            {"is_important": True},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["data"]["is_important"])
        # BR-084: edits to published announcements are auditable.
        self.assertTrue(
            AuditEvent.objects.filter(
                action="announcement_updated", resource_id=str(target.pk)
            ).exists()
        )
