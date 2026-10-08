"""Query-count regression tests for coursework list serialization.

The release N+1 audit found per-row queries in ``list_assignments`` (two
counts plus one latest-submission lookup per assignment) and ``list_sheets``
(two mark counts per sheet). The serializers now prefer annotated aggregates
and one bulk latest-submission fetch, falling back to queries only for
single-object callers.

These tests pin the scaling property, not an exact number: doubling the rows
must not add queries. An exact count would brittlely couple the suite to
unrelated query changes; the equality below fails if and only if a per-row
query returns. Payload correctness rides along so the optimization cannot
silently change the figures.
"""

from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academic.models import (
    Course,
    CourseOffering,
    Department,
    Enrollment,
    SchoolYear,
    Semester,
)
from apps.accounts.models import User

from .models import AssessmentMark, AssessmentSheet, Assignment, Submission
from .services.coursework_service import list_assignments, list_sheets


def count_queries(callable_, *args, **kwargs):
    with CaptureQueriesContext(connection) as context:
        result = callable_(*args, **kwargs)
    return len(context), result


class CourseworkQueryCountFixture(TestCase):
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
            "qc-lect@fet.edu", "qc-lect", "Qc", "Lect", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "qc-stu@fet.edu", "qc-stu", "Qc", "Stu", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.course = Course.objects.create(
            code="QC401", name="Query Counts", department=self.department
        )
        self.offering = CourseOffering.objects.create(
            course=self.course,
            semester=self.semester,
            department=self.department,
            lecturer=self.lecturer,
        )
        Enrollment.objects.create(
            student=self.student, course=self.course, course_offering=self.offering
        )

    def make_assignments(self, n, *, with_submissions=True):
        rows = []
        for index in range(n):
            assignment = Assignment.objects.create(
                course_offering=self.offering,
                title=f"Assignment {index}",
                created_by=self.lecturer,
            )
            if with_submissions:
                Submission.objects.create(
                    assignment=assignment,
                    student=self.student,
                    note=f"attempt {index}",
                    status=(
                        Submission.Status.GRADED
                        if index % 2 == 0
                        else Submission.Status.SUBMITTED
                    ),
                )
            rows.append(assignment)
        return rows


class AssignmentListQueryTests(CourseworkQueryCountFixture):
    def test_staff_list_cost_is_constant_in_assignment_count(self):
        self.make_assignments(2)
        small_queries, small_rows = count_queries(
            list_assignments, user=self.lecturer, offering_id=self.offering.pk
        )
        self.assertEqual(len(small_rows), 2)
        self.assertTrue(all(row["submissions_count"] == 1 for row in small_rows))

        self.make_assignments(4)
        large_queries, large_rows = count_queries(
            list_assignments, user=self.lecturer, offering_id=self.offering.pk
        )
        self.assertEqual(len(large_rows), 6)
        # Tripling the rows must not add a single query.
        self.assertEqual(small_queries, large_queries)
        self.assertLessEqual(large_queries, 12)

    def test_student_list_bulk_fetches_latest_submissions(self):
        assignments = self.make_assignments(3)
        queries, rows = count_queries(
            list_assignments, user=self.student, offering_id=self.offering.pk
        )
        self.assertEqual(len(rows), 3)
        by_id = {row["id"]: row for row in rows}
        for assignment in assignments:
            mine = by_id[str(assignment.pk)]["my_submission"]
            self.assertIsNotNone(mine)
            self.assertEqual(mine["student"], str(self.student.pk))

        self.make_assignments(3)
        more_queries, more_rows = count_queries(
            list_assignments, user=self.student, offering_id=self.offering.pk
        )
        self.assertEqual(len(more_rows), 6)
        self.assertEqual(queries, more_queries)
        self.assertLessEqual(more_queries, 12)

    def test_student_without_submission_sees_null_my_submission(self):
        self.make_assignments(1, with_submissions=False)
        _, rows = count_queries(
            list_assignments, user=self.student, offering_id=self.offering.pk
        )
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["submissions_count"], 0)
        self.assertIsNone(rows[0]["my_submission"])


class SheetListQueryTests(CourseworkQueryCountFixture):
    def make_sheets(self, n):
        rows = []
        for index in range(n):
            sheet = AssessmentSheet.objects.create(
                course_offering=self.offering,
                title=f"CA {index}",
                created_by=self.lecturer,
            )
            AssessmentMark.objects.create(
                assessment=sheet,
                student=self.student,
                score="12.00",
                created_by=self.lecturer,
            )
            rows.append(sheet)
        return rows

    def test_sheet_list_cost_is_constant_in_sheet_count(self):
        self.make_sheets(2)
        small_queries, small_rows = count_queries(
            list_sheets, user=self.lecturer, offering_id=self.offering.pk
        )
        self.assertEqual(len(small_rows), 2)
        self.assertTrue(all(row["marks_count"] == 1 for row in small_rows))
        self.assertTrue(all(row["graded_count"] == 1 for row in small_rows))

        self.make_sheets(4)
        large_queries, large_rows = count_queries(
            list_sheets, user=self.lecturer, offering_id=self.offering.pk
        )
        self.assertEqual(len(large_rows), 6)
        self.assertEqual(small_queries, large_queries)
        self.assertLessEqual(large_queries, 12)

    def test_unscored_marks_count_towards_marks_but_not_graded(self):
        sheet = self.make_sheets(1)[0]
        mark = AssessmentMark.objects.get(assessment=sheet)
        mark.score = None
        mark.save(update_fields=["score"])
        _, rows = count_queries(
            list_sheets, user=self.lecturer, offering_id=self.offering.pk
        )
        self.assertEqual(rows[0]["marks_count"], 1)
        self.assertEqual(rows[0]["graded_count"], 0)
