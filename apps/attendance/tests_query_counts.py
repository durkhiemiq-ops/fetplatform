"""Query-count regression test for the attendance record list.

``AttendanceRecordListView`` prefetches ``corrections__corrected_by`` and
must read the correction envelope from that cache. Calling
``record.corrections.exists()`` / ``.count()`` per row re-queries the
database once or twice per record (up to ~1000 queries on a full page), so
this test pins the scaling property: quadrupling the rows must not add a
query, and the corrected flags must stay right.
"""

from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academic.models import ClassSession, Course
from apps.accounts.models import User

from .models import AttendanceCorrection, AttendanceRecord, AttendanceSession


class RecordListQueryTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.lecturer = User.objects.create_user(
            "qr-lect@fet.edu", "qr-lect", "Qr", "Lect", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.course = Course.objects.create(code="QR101", name="Query Counts")
        self.class_session = ClassSession.objects.create(
            course=self.course, lecturer=self.lecturer, starts_at=timezone.now()
        )
        self.session = AttendanceSession.objects.create(
            class_session=self.class_session,
            lecturer=self.lecturer,
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.client.force_authenticate(user=self.lecturer)
        self.url = reverse("attendance:record-list") + f"?session={self.session.pk}"

    def make_records(self, n, *, with_corrections=True):
        for index in range(n):
            student = User.objects.create_user(
                f"qr-stu-{self.session.pk}-{index}-{AttendanceRecord.objects.count()}@example.test",
                f"qrstu{AttendanceRecord.objects.count()}",
                "Qr",
                f"Stu{index}",
                "StrongPass!2026",
            )
            record = AttendanceRecord.objects.create(
                attendance_session=self.session, student=student
            )
            if with_corrections and index % 2 == 0:
                AttendanceCorrection.objects.create(
                    attendance_record=record,
                    corrected_by=self.lecturer,
                    reason="late arrival verified",
                )

    def get_rows(self):
        with CaptureQueriesContext(connection) as context:
            response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.content)
        return len(context), response.json()["data"]

    def test_record_list_cost_is_constant_in_record_count(self):
        self.make_records(1)
        small_queries, small_rows = self.get_rows()
        self.assertEqual(len(small_rows), 1)
        self.assertTrue(small_rows[0]["corrected"])
        self.assertEqual(small_rows[0]["correction_count"], 1)

        self.make_records(3)
        large_queries, large_rows = self.get_rows()
        self.assertEqual(len(large_rows), 4)
        # Quadrupling the rows must not add a single query.
        self.assertEqual(small_queries, large_queries)
        self.assertLessEqual(large_queries, 12)

    def test_uncorrected_records_report_false_and_zero(self):
        self.make_records(2, with_corrections=False)
        _, rows = self.get_rows()
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row["corrected"] is False for row in rows))
        self.assertTrue(all(row["correction_count"] == 0 for row in rows))
