"""Content-model policy: plain text, bounded, and never silently rewritten.

The agreed content model for user-authored prose — announcement bodies,
contribution notes, and private assessment notes — is **plain text plus output
encoding**. The server deliberately does not strip ``<``/``>``: stripping would
corrupt legitimate text and is not what prevents XSS. React escaping those
strings at render time is, and the static gate in
``scripts/security_audit_checks.py`` (check 10) is what keeps every render path
a text node so that escaping is actually reached.

Two properties follow, and both are easy to break without noticing:

* **Nothing is rewritten.** A payload containing markup must survive storage
  and serialization byte-for-byte. A test that only asserted a successful
  status would still pass if the server were mangling content.
* **Nothing is unbounded.** Every write path refuses an oversized body, so one
  request cannot park an arbitrary volume in the database. The bounds are
  defensive rather than a product requirement, which is why each is a named
  constant shared between a model and its serializers instead of a literal
  repeated in several places.
"""

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import ClassSession, Course, Department, Faculty
from apps.announcements.models import Announcement, BODY_MAX_LENGTH
from apps.announcements.serializers import AnnouncementCreateSerializer
from apps.assessments.models import Assessment, PRIVATE_NOTES_MAX_LENGTH
from apps.projects.models import CONTRIBUTION_NOTES_MAX_LENGTH
from apps.projects.serializers import ContributionReviewSerializer

#: A payload that must be stored exactly as given. It is hostile in intent and
#: harmless in fact: nothing here executes, because the value is only ever
#: rendered as text.
MARKUP = '<script>alert("xss")</script> <img src=x onerror="alert(1)"> & <b>bold</b>'


class PlainTextRoundTripTests(TestCase):
    """Markup reaches the database unchanged — no stripping, no rewriting."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.faculty = Faculty.objects.create(name="Engineering")
        self.lecturer = User.objects.create_user(
            "content-lect@fet.edu", "content-lect", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.lecturer.faculty = self.faculty
        self.lecturer.save()
        self.student = User.objects.create_user(
            "content-stu@fet.edu", "content-stu", "Stu", "Dent", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.department = Department.objects.create(
            name="Computer Science", faculty=self.faculty
        )
        self.course = Course.objects.create(
            code="CS101", name="Foundations", department=self.department
        )
        # A lecturer may only assess a course they actually teach: the
        # responsibility check looks for a class session or offering they own,
        # not for a faculty or department match.
        ClassSession.objects.create(
            course=self.course, lecturer=self.lecturer, starts_at=timezone.now()
        )

    def test_announcement_body_round_trips_markup_verbatim(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("announcements:list"),
            {
                "title": "Exam room change",
                "body": MARKUP,
                "scope": "faculty",
                "scope_id": str(self.faculty.pk),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.content)
        # Serialized straight back out of the model, byte-for-byte.
        self.assertEqual(response.data["data"]["body"], MARKUP)

        stored = Announcement.objects.get(pk=response.data["data"]["id"])
        self.assertEqual(stored.body, MARKUP)
        # The angle brackets are still there: this proves the *server* did not
        # sanitise, which is exactly the behaviour the policy relies on.
        self.assertIn("<script>", stored.body)

    def test_announcement_update_does_not_rewrite_the_body(self):
        self.client.force_authenticate(user=self.lecturer)
        created = self.client.post(
            reverse("announcements:list"),
            {
                "title": "Room change",
                "body": "original body",
                "scope": "faculty",
                "scope_id": str(self.faculty.pk),
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        pk = created.data["data"]["id"]

        response = self.client.patch(
            reverse("announcements:detail", args=[pk]),
            {"body": MARKUP},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["data"]["body"], MARKUP)

    def test_private_notes_round_trip_markup_for_staff(self):
        # Created through the API rather than the ORM: the read path scopes to
        # assessments the lecturer manages, which is derived from the creating
        # user, so an ORM row with no ``created_by`` would simply be invisible.
        self.client.force_authenticate(user=self.lecturer)
        created = self.client.post(
            reverse("assessments:list"),
            {
                "student": str(self.student.pk),
                "course": str(self.course.pk),
                "private_notes": MARKUP,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        self.assertEqual(created.data["data"]["private_notes"], MARKUP)

        response = self.client.get(reverse("assessments:list"))
        self.assertEqual(response.status_code, 200, response.content)
        rows = {str(row["id"]): row for row in response.data["data"]}
        pk = str(created.data["data"]["id"])
        self.assertIn(pk, rows)
        self.assertEqual(rows[pk]["private_notes"], MARKUP)


class ContentBoundTests(TestCase):
    """Every write path refuses a body larger than its declared bound."""

    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.faculty = Faculty.objects.create(name="Engineering")
        self.lecturer = User.objects.create_user(
            "bound-lect@fet.edu", "bound-lect", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.lecturer.faculty = self.faculty
        self.lecturer.save()
        self.student = User.objects.create_user(
            "bound-stu@fet.edu", "bound-stu", "Stu", "Dent", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.department = Department.objects.create(
            name="Computer Science", faculty=self.faculty
        )
        self.course = Course.objects.create(
            code="CS102", name="Systems", department=self.department
        )
        ClassSession.objects.create(
            course=self.course, lecturer=self.lecturer, starts_at=timezone.now()
        )

    def _create_announcement(self, body):
        self.client.force_authenticate(user=self.lecturer)
        return self.client.post(
            reverse("announcements:list"),
            {
                "title": "Notice",
                "body": body,
                "scope": "faculty",
                "scope_id": str(self.faculty.pk),
            },
            format="json",
        )

    def test_announcement_create_refuses_an_oversized_body(self):
        response = self._create_announcement("x" * (BODY_MAX_LENGTH + 1))
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "INVALID_DATA")
        self.assertEqual(Announcement.objects.count(), 0)

    def test_announcement_body_at_the_bound_is_accepted(self):
        # The bound must reject an overrun, not quietly reject everything.
        response = self._create_announcement("x" * BODY_MAX_LENGTH)
        self.assertEqual(response.status_code, 201, response.content)

    def test_announcement_update_refuses_an_oversized_body(self):
        created = self._create_announcement("small")
        self.assertEqual(created.status_code, 201, created.content)
        pk = created.data["data"]["id"]

        response = self.client.patch(
            reverse("announcements:detail", args=[pk]),
            {"body": "y" * (BODY_MAX_LENGTH + 1)},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "INVALID_DATA")

        stored = Announcement.objects.get(pk=pk)
        # The existing body survived the rejected edit.
        self.assertEqual(stored.body, "small")

    def test_assessment_create_refuses_oversized_private_notes(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.post(
            reverse("assessments:list"),
            {
                "student": str(self.student.pk),
                "course": str(self.course.pk),
                "private_notes": "n" * (PRIVATE_NOTES_MAX_LENGTH + 1),
            },
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertFalse(response.data["success"])
        self.assertEqual(Assessment.objects.count(), 0)

    def test_assessment_update_refuses_oversized_private_notes(self):
        # Same scoping as above: created through the API so the lecturer owns
        # it and the update path can reach it at all.
        self.client.force_authenticate(user=self.lecturer)
        created = self.client.post(
            reverse("assessments:list"),
            {
                "student": str(self.student.pk),
                "course": str(self.course.pk),
                "private_notes": "keep me",
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        pk = created.data["data"]["id"]

        response = self.client.patch(
            reverse("assessments:detail", args=[pk]),
            {"private_notes": "n" * (PRIVATE_NOTES_MAX_LENGTH + 1)},
            format="json",
        )
        self.assertEqual(response.status_code, 400, response.content)
        assessment = Assessment.objects.get(pk=pk)
        self.assertEqual(assessment.private_notes, "keep me")

    def test_contribution_notes_are_bounded(self):
        # Serializer-level rather than HTTP: the contribution write path needs
        # a project, group, membership and pending contribution to reach this
        # field, and the bound lives in the serializer regardless of the
        # fixture it is reached through.
        over = ContributionReviewSerializer(
            data={"approved": True, "notes": "z" * (CONTRIBUTION_NOTES_MAX_LENGTH + 1)}
        )
        self.assertFalse(over.is_valid())
        self.assertIn("notes", over.errors)

        at_bound = ContributionReviewSerializer(
            data={"approved": True, "notes": "z" * CONTRIBUTION_NOTES_MAX_LENGTH}
        )
        self.assertTrue(at_bound.is_valid(), at_bound.errors)

    def test_announcement_serializer_is_the_single_source_of_the_bound(self):
        # Guards the shared-constant design: if the serializer ever declares a
        # bound that disagrees with the model, requests would be accepted or
        # refused by a different rule than the one documented on the model.
        field = AnnouncementCreateSerializer().fields["body"]
        self.assertEqual(field.max_length, BODY_MAX_LENGTH)
