"""API + service tests for the notifications inbox and its real triggers.

Covers the API §45 contract (GET list / PATCH {id}/read / POST read-all),
the §25 permission-denial rule (another user's notification is a 404 that is
byte-identical to a nonexistent one), the §67 trimmed response shape, and the
five wired triggers: announcement published, BR-064 flag raised, role changed,
enrollment added, and attendance corrected.
"""

from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academic.models import ClassSession, Course, Department, Enrollment, Faculty
from apps.accounts.models import User
from apps.announcements.models import Announcement
from apps.announcements.services.announcement_service import (
    create_announcement,
    update_announcement,
)
from apps.attendance.models import (
    AttendanceCheckpoint,
    AttendanceRecord,
    AttendanceSession,
)
from apps.attendance.services.attendance_service import (
    correct_attendance,
    flag_suspicious_activity,
)
from apps.notifications.models import Notification
from apps.notifications.services.notification_service import (
    create_notification,
    get_owned_notification,
    list_notifications,
    mark_all_read,
    mark_read,
)
from apps.academic.services.enrollment_service import enroll_student_in_course
from apps.accounts.services.auth_service import change_user_role

from core.models import AuditEvent

EXPECTED_FIELDS = {
    "id",
    "category",
    "title",
    "body",
    "related_type",
    "related_id",
    "is_read",
    "read_at",
    "created_at",
}


class NotificationServiceTests(TestCase):
    def setUp(self):
        self.student = User.objects.create_user(
            "student@example.test", "student", "Stu", "Dent", "StrongPass!2026"
        )
        self.other = User.objects.create_user(
            "other@example.test", "otheruser", "Other", "User", "StrongPass!2026"
        )

    def test_create_validation(self):
        from apps.notifications.services.notification_service import InvalidNotificationError

        with self.assertRaises(InvalidNotificationError):
            create_notification(recipient=None, category="announcement", title="t", body="b")
        with self.assertRaises(InvalidNotificationError):
            create_notification(
                recipient=self.student, category="not-a-category", title="t", body="b"
            )
        with self.assertRaises(InvalidNotificationError):
            create_notification(
                recipient=self.student, category="announcement", title="   ", body="b"
            )
        with self.assertRaises(InvalidNotificationError):
            create_notification(
                recipient=self.student, category="announcement", title="t", body=""
            )

    def test_inbox_is_owner_scoped(self):
        create_notification(
            recipient=self.student,
            category="announcement",
            title="For student",
            body="body",
        )
        create_notification(
            recipient=self.other,
            category="role_change",
            title="For other",
            body="body",
        )
        student_rows = list_notifications(recipient=self.student)
        self.assertEqual([n.title for n in student_rows], ["For student"])
        other_rows = list_notifications(recipient=self.other)
        self.assertEqual([n.title for n in other_rows], ["For other"])

    def test_get_owned_absent_and_foreign_both_none(self):
        mine = create_notification(
            recipient=self.student, category="announcement", title="Mine", body="b"
        )
        self.assertIsNotNone(
            get_owned_notification(notification_id=mine.id, recipient=self.student)
        )
        # Another user's notification, and a random uuid, must both look absent.
        self.assertIsNone(
            get_owned_notification(notification_id=mine.id, recipient=self.other)
        )
        self.assertIsNone(
            get_owned_notification(notification_id="00000000-0000-0000-0000-000000000001",
                                  recipient=self.student)
        )

    def test_mark_read_idempotent(self):
        item = create_notification(
            recipient=self.student, category="announcement", title="Mine", body="b"
        )
        first = mark_read(notification_id=item.id, recipient=self.student)
        self.assertTrue(first.is_read)
        self.assertIsNotNone(first.read_at)
        read_at_first = first.read_at
        second = mark_read(notification_id=item.id, recipient=self.student)
        self.assertTrue(second.is_read)
        self.assertEqual(second.read_at, read_at_first)

    def test_mark_all_read_counts(self):
        create_notification(recipient=self.student, category="announcement", title="a", body="b")
        create_notification(recipient=self.student, category="enrollment", title="b", body="c")
        create_notification(recipient=self.student, category="enrollment", title="c", body="d")
        self.assertEqual(mark_all_read(recipient=self.student), 3)
        self.assertEqual(mark_all_read(recipient=self.student), 0)
        self.assertTrue(
            all(
                n.is_read
                for n in Notification.objects.filter(recipient=self.student)
            )
        )


class AnnouncementTriggerTests(TestCase):
    """BR §23 example: a course announcement reaches enrolled students only."""

    def setUp(self):
        self.admin = User.objects.create_user(
            "admin@example.test", "administrator", "Ad", "Min", "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )
        self.enrolled = User.objects.create_user(
            "enrolled@example.test", "enrolled", "En", "Rolled", "StrongPass!2026"
        )
        self.not_enrolled = User.objects.create_user(
            "outsider@example.test", "outsider", "Out", "Sider", "StrongPass!2026"
        )
        self.course = Course.objects.create(code="NTF101", name="Notifications")
        Enrollment.objects.create(student=self.enrolled, course=self.course, is_active=True)

    def _announcement(self, **kwargs):
        return Announcement.objects.create(
            title=kwargs.pop("title", "Mid-semester update"),
            body=kwargs.pop("body", "Please check the portal."),
            scope=kwargs.pop("scope", "course"),
            course_id=kwargs.pop("course_id", None) or self.course.id,
            is_published=kwargs.pop("is_published", False),
            **kwargs,
        )

    def test_publish_fans_out_to_enrolled_students_only(self):
        announcement = create_announcement(
            AnnouncementModel=Announcement,
            title="Mid-semester update",
            body="Please check the portal.",
            scope="course",
            scope_id=self.course.id,
            actor=self.admin,
            published=True,
        )
        self.assertTrue(announcement.is_published)
        self.assertEqual(
            list(
                Notification.objects.filter(
                    recipient=self.enrolled, category="announcement"
                ).values_list("related_id", flat=True)
            ),
            [str(announcement.id)],
        )
        self.assertFalse(
            Notification.objects.filter(recipient=self.not_enrolled).exists()
        )

    def test_draft_create_publishes_nothing(self):
        create_announcement(
            AnnouncementModel=Announcement,
            title="Draft",
            body="Not ready.",
            scope="course",
            scope_id=self.course.id,
            actor=self.admin,
            published=False,
        )
        self.assertEqual(Notification.objects.count(), 0)

    def test_draft_to_published_transition_notifies_once(self):
        draft = create_announcement(
            AnnouncementModel=Announcement,
            title="Draft",
            body="Not ready.",
            scope="course",
            scope_id=self.course.id,
            actor=self.admin,
            published=False,
        )
        self.assertEqual(Notification.objects.count(), 0)

        updated = update_announcement(
            announcement=draft,
            actor=self.admin,
            published=True,
        )
        self.assertTrue(updated.is_published)
        self.assertEqual(Notification.objects.count(), 1)
        self.assertEqual(Notification.objects.get().recipient, self.enrolled)

        # Editing an already-published announcement must NOT re-notify.
        update_announcement(
            announcement=updated,
            actor=self.admin,
            title="Edited headline",
            published=True,
        )
        self.assertEqual(Notification.objects.count(), 1)

    def test_department_scope_notifies_matching_accounts(self):
        dept = Department.objects.create(name="Computer Science")
        dept_member = User.objects.create_user(
            "cs@example.test", "csdept", "Cs", "Member", "StrongPass!2026",
            department=dept,
        )
        outsider = User.objects.create_user(
            "ee@example.test", "eedept", "Ee", "Member", "StrongPass!2026"
        )
        announcement = create_announcement(
            AnnouncementModel=Announcement,
            title="Department meeting",
            body="All staff please attend.",
            scope="department",
            scope_id=dept.id,
            actor=self.admin,
            published=True,
        )
        self.assertEqual(
            set(
                Notification.objects.filter(
                    category="announcement"
                ).values_list("recipient_id", flat=True)
            ),
            {dept_member.id},
        )
        self.assertNotIn(outsider.id, Notification.objects.values_list("recipient_id", flat=True))
        self.assertIsNotNone(announcement.id)

    def test_faculty_scope_notifies_matching_accounts(self):
        faculty = Faculty.objects.create(name="Engineering")
        faculty_member = User.objects.create_user(
            "eng@example.test", "engfaculty", "Eng", "Member", "StrongPass!2026",
            faculty=faculty,
        )
        create_announcement(
            AnnouncementModel=Announcement,
            title="Faculty notice",
            body="All faculty.",
            scope="faculty",
            scope_id=faculty.id,
            actor=self.admin,
            published=True,
        )
        self.assertEqual(
            list(Notification.objects.values_list("recipient_id", flat=True)),
            [faculty_member.id],
        )


class DomainTriggerTests(TestCase):
    """The other four wired triggers: flag, correction, role change, enrollment."""

    def setUp(self):
        self.student = User.objects.create_user(
            "student@example.test", "student", "Stu", "Dent", "StrongPass!2026"
        )
        self.lecturer = User.objects.create_user(
            "lecturer@example.test", "lecturer", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.admin = User.objects.create_user(
            "admin@example.test", "administrator", "Ad", "Min", "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )
        self.course = Course.objects.create(code="TRG101", name="Triggers")
        self.class_session = ClassSession.objects.create(
            course=self.course, lecturer=self.lecturer, starts_at=timezone.now()
        )

    def _record(self):
        session = AttendanceSession.objects.create(
            class_session=self.class_session,
            lecturer=self.lecturer,
            status=AttendanceSession.Status.ACTIVE,
            expires_at=timezone.now() + timedelta(seconds=60),
        )
        checkpoint = AttendanceCheckpoint.objects.create(
            attendance_session=session, student=self.student
        )
        return AttendanceRecord.objects.create(
            attendance_session=session,
            student=self.student,
            checkpoint=checkpoint,
        )

    def test_flag_notifies_flagged_account(self):
        flag_suspicious_activity(
            actor_id=self.student.id,
            reason="repeated_invalid_attendance_scan",
            metadata={"failure_code": "TOKEN_ALREADY_USED", "request_ip": "10.0.0.1"},
        )
        items = Notification.objects.filter(recipient=self.student)
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.get().category, "attendance_flag")
        self.assertIn("TOKEN_ALREADY_USED", items.get().body)

    def test_flag_missing_account_is_silent(self):
        # A flag for a deleted/absent account is still audited, but no
        # notification row is created (no eligible recipient exists).
        flag_suspicious_activity(
            actor_id="00000000-0000-0000-0000-000000000099",
            reason="repeated_invalid_attendance_scan",
        )
        self.assertEqual(Notification.objects.count(), 0)
        self.assertTrue(AuditEvent.objects.filter(action="attendance_suspicious_activity").exists())

    def test_correction_notifies_record_student(self):
        record = self._record()
        correction = correct_attendance(
            record=record,
            lecturer=self.lecturer,
            new_status="EXCUSED",
            reason="Marked excused after a medical note",
        )
        items = Notification.objects.filter(recipient=self.student)
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.get().category, "attendance_correction")
        self.assertEqual(items.get().related_id, str(record.id))
        self.assertIsNotNone(correction.id)
        # The correction carries the transition it describes, so the student's
        # notification is traceable back to what actually changed.
        self.assertEqual(correction.old_status, AttendanceRecord.Status.PRESENT)
        self.assertEqual(correction.new_status, AttendanceRecord.Status.EXCUSED)

    def test_role_change_notifies_target_account(self):
        target = User.objects.create_user(
            "target@example.test", "target", "Tar", "Get", "StrongPass!2026"
        )
        change_user_role(target, "LECTURER", actor=self.admin)
        self.assertEqual(target.role, "LECTURER")
        items = Notification.objects.filter(recipient=target)
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.get().category, "role_change")
        self.assertIn("LECTURER", items.get().body)
        # The admin actor never receives a role-change notification about
        # someone else's account.
        self.assertFalse(Notification.objects.filter(recipient=self.admin).exists())

    def test_enrollment_notifies_student(self):
        authz = lambda **kwargs: True
        enroll_student_in_course(
            self.student.id,
            self.course.id,
            EnrollmentModel=Enrollment,
            StudentModel=User,
            CourseModel=Course,
            actor_id=self.admin.id,
            reason="session enrollment",
            authorization_checker=authz,
        )
        items = Notification.objects.filter(recipient=self.student)
        self.assertEqual(items.count(), 1)
        self.assertEqual(items.get().category, "enrollment")
        self.assertEqual(items.get().related_id, str(self.course.id))

    def test_duplicate_enrollment_does_not_double_notify(self):
        from apps.academic.services.enrollment_service import AlreadyEnrolledError

        authz = lambda **kwargs: True
        enroll_student_in_course(
            self.student.id, self.course.id,
            EnrollmentModel=Enrollment, StudentModel=User, CourseModel=Course,
            actor_id=self.admin.id, authorization_checker=authz,
        )
        with self.assertRaises(AlreadyEnrolledError):
            enroll_student_in_course(
                self.student.id, self.course.id,
                EnrollmentModel=Enrollment, StudentModel=User, CourseModel=Course,
                actor_id=self.admin.id, authorization_checker=authz,
            )
        self.assertEqual(
            Notification.objects.filter(recipient=self.student, category="enrollment").count(),
            1,
        )


class NotificationApiTests(TestCase):
    """API §45 contract + §25 denial + §67 response shape."""

    def setUp(self):
        self.student = User.objects.create_user(
            "student@example.test", "student", "Stu", "Dent", "StrongPass!2026"
        )
        self.other = User.objects.create_user(
            "other@example.test", "otheruser", "Other", "User", "StrongPass!2026"
        )
        self.mine = create_notification(
            recipient=self.student,
            category="announcement",
            title="For student",
            body="body one",
            related_type="announcement",
            related_id="00000000-0000-0000-0000-00000000000a",
        )
        create_notification(
            recipient=self.other,
            category="enrollment",
            title="For other",
            body="body two",
        )

    def auth(self, user):
        client = APIClient()
        client.force_authenticate(user=user)
        return client

    # ---- GET list ---------------------------------------------------------

    def test_list_shape_and_owner_scoping(self):
        response = self.auth(self.student).get(reverse("notifications:list"))
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(len(body["data"]), 1)
        row = body["data"][0]
        # §67: exactly the trimmed fields a notification UI needs.
        self.assertEqual(set(row.keys()), EXPECTED_FIELDS)
        self.assertNotIn("recipient", row)
        self.assertEqual(row["title"], "For student")
        self.assertEqual(row["category"], "announcement")
        self.assertFalse(row["is_read"])

    def test_list_unread_filter(self):
        mark_read(notification_id=self.mine.id, recipient=self.student)
        response = self.auth(self.student).get(
            reverse("notifications:list"), {"unread": "true"}
        )
        body = response.json()
        self.assertEqual(body["data"], [])
        full = self.auth(self.student).get(reverse("notifications:list"))
        self.assertEqual(len(full.json()["data"]), 1)

    def test_list_newest_first(self):
        create_notification(
            recipient=self.student, category="enrollment", title="Older", body="x"
        )
        Notification.objects.filter(recipient=self.student, title="Older").update(
            created_at=timezone.now() - timedelta(minutes=5)
        )
        create_notification(
            recipient=self.student, category="role_change", title="Newer", body="y"
        )
        response = self.auth(self.student).get(reverse("notifications:list"))
        titles = [row["title"] for row in response.json()["data"]]
        self.assertEqual(titles, ["Newer", "For student", "Older"])

    # ---- PATCH read -------------------------------------------------------

    def test_read_own(self):
        response = self.auth(self.student).patch(
            reverse("notifications:read", args=[self.mine.id]), {}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        row = response.json()["data"]
        self.assertTrue(row["is_read"])
        self.assertEqual(set(row.keys()), EXPECTED_FIELDS)
        self.assertIsNotNone(row["read_at"])

    def test_read_idempotent(self):
        client = self.auth(self.student)
        first = client.patch(reverse("notifications:read", args=[self.mine.id]), {}, format="json")
        second = client.patch(reverse("notifications:read", args=[self.mine.id]), {}, format="json")
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            first.json()["data"]["read_at"], second.json()["data"]["read_at"]
        )

    def test_read_foreign_and_nonexistent_both_404_identical(self):
        # §25: someone else's notification and a random uuid produce the exact
        # same NOT_FOUND body — no existence information leaks.
        foreign_id = Notification.objects.get(recipient=self.other).id
        foreign = self.auth(self.student).patch(
            reverse("notifications:read", args=[foreign_id]), {}, format="json"
        )
        missing = self.auth(self.student).patch(
            reverse("notifications:read", args=["00000000-0000-0000-0000-0000000000ff"]),
            {},
            format="json",
        )
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(foreign.json(), missing.json())
        self.assertEqual(foreign.json()["error"]["code"], "NOT_FOUND")

    # ---- POST read-all ----------------------------------------------------

    def test_read_all(self):
        create_notification(recipient=self.student, category="enrollment", title="x", body="y")
        create_notification(recipient=self.student, category="role_change", title="z", body="w")
        response = self.auth(self.student).post(reverse("notifications:read-all"), {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"], {"updated_count": 3})
        again = self.auth(self.student).post(reverse("notifications:read-all"), {}, format="json")
        self.assertEqual(again.json()["data"], {"updated_count": 0})
        self.assertFalse(
            Notification.objects.filter(recipient=self.student, is_read=False).exists()
        )
        # The other user's inbox is untouched.
        self.assertFalse(Notification.objects.get(recipient=self.other).is_read)

    # ---- Auth -------------------------------------------------------------

    def test_unauthenticated_access_rejected(self):
        # Platform convention (DRF 3.18 + SessionAuthentication): unauthenticated
        # access is coerced to 403 because session auth has no WWW-Authenticate
        # header.  The whole codebase relies on this behavior.
        client = APIClient()
        for url, method in [
            (reverse("notifications:list"), "get"),
            (reverse("notifications:read", args=[self.mine.id]), "patch"),
            (reverse("notifications:read-all"), "post"),
        ]:
            response = getattr(client, method)(url, {}, format="json")
            self.assertEqual(response.status_code, 403, msg=url)
            self.assertEqual(response.json()["error"]["code"], "FORBIDDEN", msg=url)