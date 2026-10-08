"""The sheet contract the mark sheet UI actually reads and writes.

Two long-standing mismatches between ``AssessmentPanel`` and the sheet
endpoint, both invisible to the server and visible to a lecturer:

* the panel renders ``graded_count/marks_count marked`` for every sheet, but
  ``_serialize_sheet`` never emitted ``graded_count`` — so every row read
  ``undefined/12`` and the "Enter / edit marks" button read
  ``(undefined/12)``;
* the create form posted ``description``, ``raw_maximum`` and ``attachment``.
  ``AssessmentSheet`` has no such columns, the view read four named keys and
  ignored the rest, so a lecturer could type notes, choose a conversion scale
  and attach a file and get a 201 that stored none of it — the attachment
  upload even left an orphan file behind.

``graded_count`` is derived (a mark counts once it carries a score); the
unsupported fields are now an explicit 400 instead of a quiet no-op, matching
the rule ``update_group`` already applies to group metadata.
"""

from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academic.models import (
    Course,
    CourseOffering,
    Department,
    Enrollment,
    SchoolYear,
    Semester,
)

from .models import AssessmentSheet


class SheetContractFixture(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

        self.department = Department.objects.create(name="Engineering", code="ENG")
        year = SchoolYear.objects.create(
            name="2026/2027",
            start_date=timezone.now().date() - timedelta(days=100),
            end_date=timezone.now().date() + timedelta(days=200),
        )
        self.semester = Semester.objects.create(
            school_year=year,
            name="Semester 1",
            start_date=timezone.now().date() - timedelta(days=20),
            end_date=timezone.now().date() + timedelta(days=80),
            is_current=True,
        )
        self.lecturer = User.objects.create_user(
            "sc-lect@fet.edu", "sc-lect", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.students = [
            User.objects.create_user(
                f"sc-stu{i}@fet.edu", f"sc-stu{i}", "Stu", f"Dent{i}", "StrongPass!2026",
                role=User.Role.STUDENT,
            )
            for i in (1, 2)
        ]
        self.course = Course.objects.create(
            code="CS301", name="Operating Systems", department=self.department
        )
        self.offering = CourseOffering.objects.create(
            course=self.course,
            semester=self.semester,
            department=self.department,
            lecturer=self.lecturer,
        )
        for student in self.students:
            Enrollment.objects.create(
                student=student, course=self.course, course_offering=self.offering
            )

        self.client.force_authenticate(user=self.lecturer)

    # -- helpers ----------------------------------------------------------

    def create(self, payload):
        return self.client.post(
            reverse("offering-assessment-sheets", args=[self.offering.pk]),
            payload,
            format="json",
        )

    def listing(self):
        response = self.client.get(
            reverse("offering-assessment-sheets", args=[self.offering.pk])
        )
        assert response.status_code == 200, response.content
        return response.json()["data"]

    def put_marks(self, sheet, marks):
        return self.client.put(
            reverse("assessment-sheet-marks", args=[sheet.pk]),
            {"marks": marks},
            format="json",
        )


class GradedCountTests(SheetContractFixture):
    def test_new_sheet_reports_zero_of_zero(self):
        created = self.create({"title": "CA 1", "category": "CA"})
        self.assertEqual(created.status_code, 201, created.content)
        self.assertIn("graded_count", created.data["data"])
        self.assertEqual(created.data["data"]["graded_count"], 0)
        self.assertEqual(created.data["data"]["marks_count"], 0)

    def test_graded_count_counts_only_marks_that_carry_a_score(self):
        sheet_id = self.create({"title": "CA 1", "category": "CA"}).data["data"]["id"]
        sheet = AssessmentSheet.objects.get(pk=sheet_id)

        rows = [
            {"student": str(self.students[0].pk), "score": "21"},
            {"student": str(self.students[1].pk), "score": None},
        ]
        saved = self.put_marks(sheet, rows)
        self.assertEqual(saved.status_code, 200, saved.content)

        row = next(r for r in self.listing() if r["id"] == str(sheet_id))
        # Both students have a row; only one has been marked.
        self.assertEqual(row["marks_count"], 2)
        self.assertEqual(row["graded_count"], 1)

    def test_a_cleared_mark_stops_counting_as_graded(self):
        sheet_id = self.create({"title": "CA 1", "category": "CA"}).data["data"]["id"]
        sheet = AssessmentSheet.objects.get(pk=sheet_id)
        student = str(self.students[0].pk)

        self.put_marks(sheet, [{"student": student, "score": "21"}])
        self.assertEqual(
            next(r for r in self.listing() if r["id"] == str(sheet_id))["graded_count"],
            1,
        )

        self.put_marks(sheet, [{"student": student, "score": None}])
        row = next(r for r in self.listing() if r["id"] == str(sheet_id))
        self.assertEqual(row["graded_count"], 0)
        self.assertEqual(row["marks_count"], 1)


class UnknownSheetFieldTests(SheetContractFixture):
    def test_a_field_the_sheet_model_does_not_have_is_refused(self):
        for field in ("description", "raw_maximum", "attachment"):
            with self.subTest(field=field):
                response = self.create({"title": f"CA {field}", field: "anything"})
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(
                    response.json()["error"]["code"], "INVALID_INPUT"
                )
                self.assertIn(field, response.json()["error"]["message"])

        # Nothing was created by any of the refusals.
        self.assertEqual(AssessmentSheet.objects.count(), 0)

    def test_several_unknown_fields_are_all_named_in_one_answer(self):
        response = self.create(
            {"title": "CA 1", "description": "x", "raw_maximum": "40"}
        )
        self.assertEqual(response.status_code, 400, response.content)
        message = response.json()["error"]["message"]
        self.assertIn("description", message)
        self.assertIn("raw_maximum", message)

    def test_the_supported_fields_still_create_a_sheet(self):
        response = self.create(
            {
                "title": "CA 1",
                "category": "CA",
                "maximum_score": "30",
                "weight": "40",
            }
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.data["data"]
        self.assertEqual(data["title"], "CA 1")
        self.assertEqual(data["category"], "CA")
        self.assertEqual(Decimal(data["maximum_score"]), Decimal("30"))
        self.assertEqual(Decimal(data["weight"]), Decimal("40"))
