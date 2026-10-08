"""Compatibility routes and the authoritative CSV export.

No specification defines either surface — both were derived from the client's
own calls in ``frontend/src/lib/learning.js`` — so these tests are what pins
them down. They lean on the properties that would hurt most if they were
wrong:

* **The aliases are aliases.** ``/course-offerings/<id>/assessments/``,
  ``/assessments/<id>/`` and ``/assessments/<id>/marks/`` are spellings the
  client already uses. Every one of them must resolve to the canonical view
  and therefore to the same service call, so a rule can never come to exist in
  two places. If an alias and its canonical route ever answer differently,
  these tests fail.
* **Ownership is decided by the table, not the id.** The dispatcher claims a
  row by asking which table holds it. A sheet id must keep behaving like a
  sheet, and a released-results id must keep behaving like released results,
  through both spellings.
* **Failure is closed and indistinguishable.** A malformed id, a well-formed
  id nobody created, and a real id the caller may not see must all produce the
  same envelope with the same body, so neither route can be used to probe
  (§25).
* **One export.** Both export paths are byte-identical, carry a fixed column
  order, escape what a spreadsheet would otherwise evaluate, and are confined
  to the offering that owns the sheet.
"""

import csv
import io

from django.urls import reverse

from apps.assessments.models import Assessment
from apps.assessments.services import coursework_service as service

from .models import AssessmentGroup, AssessmentMark, AssessmentSheet, Assignment
from .tests_coursework import MISSING_UUID, CourseworkFixture

# Pinned literally rather than imported from the service: the service's own
# constant cannot be the thing that catches the service changing its mind.
EXPORT_COLUMNS = [
    "course_offering_id",
    "sheet_id",
    "sheet_title",
    "sheet_category",
    "student_id",
    "matricule",
    "student_name",
    "score",
    "maximum_score",
    "comment",
    "dispute_status",
    "dispute_reason",
    "dispute_response",
    "mark_updated_at",
]

# Anything that is not a well-formed UUID.
MALFORMED_ID = "not-a-uuid"


def _rows(response):
    """Parse a CSV download response back into rows."""
    return list(csv.reader(io.StringIO(response.content.decode("utf-8"))))


class RouteAliasFixture(CourseworkFixture):
    """Shared setup: a sheet with marks, plus the client's own URL spellings."""

    # -- the client's literal spellings ----------------------------------

    @staticmethod
    def _alias_sheet_list_url(offering):
        return f"/api/v1/course-offerings/{offering.pk}/assessments/"

    @staticmethod
    def _alias_sheet_url(sheet):
        return f"/api/v1/assessments/{sheet.pk}/"

    @staticmethod
    def _alias_marks_url(sheet):
        return f"/api/v1/assessments/{sheet.pk}/marks/"

    @staticmethod
    def _alias_export_url(sheet):
        return f"/api/v1/assessments/{sheet.pk}/export.csv"

    @staticmethod
    def _alias_sheet_list_literal(offering):
        return reverse("offering-assessment-sheets", args=[offering.pk])

    # -- helpers ----------------------------------------------------------

    def _marked_sheet(self, *, title="CA 1", rows=None):
        sheet = self._sheet(title=title)
        self.client.force_authenticate(user=self.lecturer)
        payload = {
            "marks": rows
            or [
                {"student": str(self.student.pk), "score": "80", "comment": "solid"},
                {"student": str(self.classmate.pk), "score": "65", "comment": ""},
            ]
        }
        response = self.client.put(
            reverse("assessment-sheet-marks", args=[sheet.pk]), payload, format="json"
        )
        assert response.status_code == 200, response.content
        return sheet

    def _group(self, *, title="Combined", sheets=None):
        self.client.force_authenticate(user=self.lecturer)
        payload = {"title": title}
        if sheets is not None:
            payload["sheets"] = [str(s.pk) for s in sheets]
        response = self.client.post(
            reverse("offering-assessment-groups", args=[self.offering.pk]),
            payload,
            format="json",
        )
        assert response.status_code == 201, response.content
        return AssessmentGroup.objects.get(pk=response.data["data"]["id"])

    def assertEnvelope404(self, response):
        self.assertEqual(response.status_code, 404, response.content)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "NOT_FOUND")


class SheetAliasTests(RouteAliasFixture):
    """The client's sheet spellings must behave exactly like the canonical ones."""

    def test_offering_sheet_list_is_identical_on_both_paths(self):
        self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        canonical = self.client.get(self._alias_sheet_list_literal(self.offering))
        alias = self.client.get(self._alias_sheet_list_url(self.offering))

        self.assertEqual(canonical.status_code, 200, canonical.content)
        self.assertEqual(alias.status_code, 200, alias.content)
        self.assertEqual(canonical.content, alias.content)

    def test_offering_sheet_create_is_identical_on_both_paths(self):
        self.client.force_authenticate(user=self.lecturer)
        payload = {"title": "CA 2", "category": "CA", "maximum_score": "50"}

        canonical = self.client.post(
            self._alias_sheet_list_literal(self.offering), payload, format="json"
        )
        alias = self.client.post(
            self._alias_sheet_list_url(self.offering), payload, format="json"
        )

        self.assertEqual(canonical.status_code, 201, canonical.content)
        self.assertEqual(alias.status_code, 201, alias.content)
        self.assertEqual(
            canonical.data["data"]["title"], alias.data["data"]["title"]
        )
        self.assertEqual(
            AssessmentSheet.objects.filter(title="CA 2").count(), 2
        )

    def test_sheet_detail_is_identical_on_both_paths(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        canonical = self.client.get(reverse("assessment-sheet-detail", args=[sheet.pk]))
        alias = self.client.get(self._alias_sheet_url(sheet))

        self.assertEqual(canonical.status_code, 200, canonical.content)
        self.assertEqual(alias.status_code, 200, alias.content)
        self.assertEqual(canonical.content, alias.content)
        # Shape check: this is a sheet, not a released-result record.
        self.assertEqual(alias.data["data"]["id"], str(sheet.pk))
        self.assertIn("category", alias.data["data"])

    def test_sheet_update_through_the_alias_reaches_the_canonical_service(self):
        sheet = self._sheet(title="Original")
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.patch(
            self._alias_sheet_url(sheet), {"title": "Renamed"}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.content)
        sheet.refresh_from_db()
        self.assertEqual(sheet.title, "Renamed")

    def test_sheet_update_through_the_alias_is_audited(self):
        sheet = self._sheet(title="Audited")
        self.client.force_authenticate(user=self.lecturer)

        self.client.patch(
            self._alias_sheet_url(sheet), {"title": "Audited twice"}, format="json"
        )

        from core.models import AuditEvent

        self.assertTrue(
            AuditEvent.objects.filter(
                action="assessment_sheet_updated", resource_type="assessment_sheet"
            ).exists()
        )

    def test_marks_are_identical_on_both_paths(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        canonical = self.client.get(
            reverse("assessment-sheet-marks", args=[sheet.pk])
        )
        alias = self.client.get(self._alias_marks_url(sheet))

        self.assertEqual(canonical.status_code, 200, canonical.content)
        self.assertEqual(alias.status_code, 200, alias.content)
        self.assertEqual(canonical.content, alias.content)

    def test_writing_marks_through_the_alias_persists_them(self):
        sheet = self._sheet()
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.put(
            self._alias_marks_url(sheet),
            {"marks": [{"student": str(self.student.pk), "score": "91"}]},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        mark = AssessmentMark.objects.get(assessment=sheet, student=self.student)
        self.assertEqual(str(mark.score), "91.00")

    def test_another_lecturer_cannot_write_through_the_alias(self):
        sheet = self._sheet()
        self.client.force_authenticate(user=self.other_lecturer)

        response = self.client.patch(
            self._alias_sheet_url(sheet), {"title": "Stolen"}, format="json"
        )

        self.assertEnvelope404(response)

    def test_foreign_write_and_missing_id_answer_identically_through_the_alias(self):
        sheet = self._sheet()
        self.client.force_authenticate(user=self.other_lecturer)

        forbidden = self.client.patch(
            self._alias_sheet_url(sheet), {"title": "Stolen"}, format="json"
        )
        missing = self.client.patch(
            f"/api/v1/assessments/{MISSING_UUID}/", {"title": "Stolen"}, format="json"
        )

        self.assertEnvelope404(forbidden)
        self.assertEnvelope404(missing)
        self.assertEqual(forbidden.content, missing.content)


class InvalidAndMissingIdTests(RouteAliasFixture):
    """Malformed, absent and invisible ids must be one and the same answer."""

    def test_malformed_id_is_identical_on_the_canonical_and_alias_paths(self):
        self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        canonical = self.client.get(
            f"/api/v1/assessment-sheets/{MALFORMED_ID}/"
        )
        alias = self.client.get(f"/api/v1/assessments/{MALFORMED_ID}/")

        self.assertEnvelope404(canonical)
        self.assertEnvelope404(alias)
        self.assertEqual(canonical.content, alias.content)

    def test_absent_id_is_identical_on_the_canonical_and_alias_paths(self):
        self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        canonical = self.client.get(f"/api/v1/assessment-sheets/{MISSING_UUID}/")
        alias = self.client.get(f"/api/v1/assessments/{MISSING_UUID}/")

        self.assertEnvelope404(canonical)
        self.assertEnvelope404(alias)
        self.assertEqual(canonical.content, alias.content)

    def test_malformed_and_absent_ids_answer_each_other_byte_for_byte(self):
        """A probe must not learn which of the two it actually hit."""
        self.client.force_authenticate(user=self.lecturer)

        malformed = self.client.get(f"/api/v1/assessments/{MALFORMED_ID}/")
        absent = self.client.get(f"/api/v1/assessments/{MISSING_UUID}/")

        self.assertEnvelope404(malformed)
        self.assertEnvelope404(absent)
        self.assertEqual(malformed.content, absent.content)

    def test_a_real_id_the_caller_may_not_see_looks_exactly_like_an_absent_one(self):
        sheet = self._sheet()
        self.client.force_authenticate(user=self.other_lecturer)

        hidden = self.client.get(f"/api/v1/assessments/{sheet.pk}/")
        absent = self.client.get(f"/api/v1/assessments/{MISSING_UUID}/")

        self.assertEnvelope404(hidden)
        self.assertEnvelope404(absent)
        self.assertEqual(hidden.content, absent.content)

    def test_marks_route_also_fails_closed_on_a_malformed_id(self):
        self.client.force_authenticate(user=self.lecturer)

        canonical = self.client.get(f"/api/v1/assessment-sheets/{MALFORMED_ID}/marks/")
        alias = self.client.get(f"/api/v1/assessments/{MALFORMED_ID}/marks/")

        self.assertEnvelope404(canonical)
        self.assertEnvelope404(alias)
        self.assertEqual(canonical.content, alias.content)

    def test_offering_route_fails_closed_on_a_malformed_id(self):
        self.client.force_authenticate(user=self.lecturer)

        canonical = self.client.get(
            f"/api/v1/course-offerings/{MALFORMED_ID}/assessment-sheets/"
        )
        alias = self.client.get(
            f"/api/v1/course-offerings/{MALFORMED_ID}/assessments/"
        )

        self.assertEnvelope404(canonical)
        self.assertEnvelope404(alias)
        self.assertEqual(canonical.content, alias.content)

    def test_group_detail_fails_closed_on_a_malformed_id(self):
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get(f"/api/v1/assessment-groups/{MALFORMED_ID}/")

        self.assertEnvelope404(response)

    def test_assignment_detail_fails_closed_on_a_malformed_id(self):
        """DELETE reaches the service, so the guard is what answers."""
        self.client.force_authenticate(user=self.lecturer)

        malformed = self.client.delete(f"/api/v1/assignments/{MALFORMED_ID}/")
        absent = self.client.delete(f"/api/v1/assignments/{MISSING_UUID}/")

        self.assertEnvelope404(malformed)
        self.assertEnvelope404(absent)
        self.assertEqual(malformed.content, absent.content)

    def test_a_malformed_assignment_id_is_indistinguishable_from_a_real_one(self):
        """A write to a foreign assignment must look like a write to nothing."""
        foreign = self._assignment(user=self.other_lecturer, offering=self.other_offering)
        self.client.force_authenticate(user=self.lecturer)

        hidden = self.client.delete(f"/api/v1/assignments/{foreign.pk}/")
        absent = self.client.delete(f"/api/v1/assignments/{MISSING_UUID}/")

        self.assertEnvelope404(hidden)
        self.assertEnvelope404(absent)
        self.assertEqual(hidden.content, absent.content)
        self.assertTrue(Assignment.objects.filter(pk=foreign.pk).exists())

    def test_getting_an_assignment_route_answers_the_same_for_every_id(self):
        """No read exists here, so 405 must not depend on which id was sent.

        The view implements no GET at all. What matters is that it says so
        identically for a real id, an absent one and a malformed one — an
        id-shaped 404/405 split would confirm which ids are real.
        """
        real = self._assignment()
        self.client.force_authenticate(user=self.lecturer)

        responses = [
            self.client.get(f"/api/v1/assignments/{real.pk}/"),
            self.client.get(f"/api/v1/assignments/{MISSING_UUID}/"),
            self.client.get(f"/api/v1/assignments/{MALFORMED_ID}/"),
        ]

        for response in responses:
            self.assertEqual(response.status_code, 405, response.content)
            self.assertFalse(response.data["success"])
            self.assertEqual(
                response.data["error"]["code"], "METHOD_NOT_ALLOWED"
            )
        self.assertEqual(responses[0].content, responses[1].content)
        self.assertEqual(responses[1].content, responses[2].content)


class RouteCollisionTests(RouteAliasFixture):
    """The dispatcher picks by table, and picks the same view every time."""

    def _assessment(self, **fields):
        defaults = {"student": self.student, "course": self.course}
        defaults.update(fields)
        return Assessment.objects.create(**defaults)

    def test_a_sheet_id_reaches_the_sheet_view(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get(self._alias_sheet_url(sheet))

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["data"]["id"], str(sheet.pk))
        self.assertNotIn("released", response.data["data"])

    def test_an_assessment_id_still_reaches_released_results(self):
        assessment = self._assessment()
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.patch(
            self._alias_sheet_url(assessment), {"released": True}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.content)
        assessment.refresh_from_db()
        self.assertTrue(assessment.released)

    def test_the_canonical_released_results_route_still_answers(self):
        assessment = self._assessment()
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.patch(
            reverse("assessments:detail", args=[assessment.pk]),
            {"released": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        assessment.refresh_from_db()
        self.assertTrue(assessment.released)

    def test_a_student_still_cannot_release_through_the_alias(self):
        assessment = self._assessment()
        self.client.force_authenticate(user=self.student)

        response = self.client.patch(
            self._alias_sheet_url(assessment), {"released": True}, format="json"
        )

        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")
        assessment.refresh_from_db()
        self.assertFalse(assessment.released)

    def test_getting_an_assessment_id_looks_like_getting_a_missing_id(self):
        """Released results are PATCH-only, so a GET must not answer 405.

        405 for an id that exists and 404 for one that does not would confirm
        which ids exist, so both are routed to the sheet view and both come
        back as the same not-found envelope.
        """
        assessment = self._assessment()
        self.client.force_authenticate(user=self.lecturer)

        existing = self.client.get(self._alias_sheet_url(assessment))
        absent = self.client.get(f"/api/v1/assessments/{MISSING_UUID}/")

        self.assertEnvelope404(existing)
        self.assertEnvelope404(absent)
        self.assertEqual(existing.content, absent.content)

    def test_the_released_results_list_route_is_not_shadowed(self):
        """The dispatcher claims only /assessments/<id>/, never /assessments/."""
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get("/api/v1/assessments/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.data["success"])

    def test_an_id_in_no_table_behaves_like_a_missing_sheet(self):
        self.client.force_authenticate(user=self.lecturer)

        orphan = self.client.get(f"/api/v1/assessments/{MISSING_UUID}/")
        sheet_miss = self.client.get(
            f"/api/v1/assessment-sheets/{MISSING_UUID}/"
        )

        self.assertEnvelope404(orphan)
        self.assertEnvelope404(sheet_miss)
        self.assertEqual(orphan.content, sheet_miss.content)


class StudentReadTests(RouteAliasFixture):
    """Students read published sheets through both spellings, and nothing else."""

    def test_a_student_reads_a_published_sheet_through_the_alias(self):
        sheet = self._marked_sheet()
        self._publish(sheet)
        self.client.force_authenticate(user=self.student)

        canonical = self.client.get(reverse("assessment-sheet-detail", args=[sheet.pk]))
        alias = self.client.get(self._alias_sheet_url(sheet))

        self.assertEqual(canonical.status_code, 200, canonical.content)
        self.assertEqual(alias.status_code, 200, alias.content)
        self.assertEqual(canonical.content, alias.content)

    def test_a_draft_sheet_is_invisible_to_a_student_on_both_paths(self):
        sheet = self._sheet()
        self.client.force_authenticate(user=self.student)

        canonical = self.client.get(reverse("assessment-sheet-detail", args=[sheet.pk]))
        alias = self.client.get(self._alias_sheet_url(sheet))

        self.assertEnvelope404(canonical)
        self.assertEnvelope404(alias)
        self.assertEqual(canonical.content, alias.content)

    def test_a_draft_and_a_missing_sheet_are_indistinguishable_to_a_student(self):
        sheet = self._sheet()
        self.client.force_authenticate(user=self.student)

        draft = self.client.get(self._alias_sheet_url(sheet))
        absent = self.client.get(f"/api/v1/assessments/{MISSING_UUID}/")

        self.assertEnvelope404(draft)
        self.assertEnvelope404(absent)
        self.assertEqual(draft.content, absent.content)

    def test_an_unenrolled_student_sees_nothing_on_either_path(self):
        sheet = self._marked_sheet()
        self._publish(sheet)
        self.client.force_authenticate(user=self.stranger)

        canonical = self.client.get(reverse("assessment-sheet-detail", args=[sheet.pk]))
        alias = self.client.get(self._alias_sheet_url(sheet))

        self.assertEnvelope404(canonical)
        self.assertEnvelope404(alias)
        self.assertEqual(canonical.content, alias.content)

    def test_a_student_cannot_edit_a_sheet_through_the_alias(self):
        sheet = self._marked_sheet()
        self._publish(sheet)
        self.client.force_authenticate(user=self.student)

        response = self.client.patch(
            self._alias_sheet_url(sheet), {"title": "Nope"}, format="json"
        )

        self.assertEqual(response.status_code, 403, response.content)
        sheet.refresh_from_db()
        self.assertEqual(sheet.title, "CA 1")


class GroupDetailTests(RouteAliasFixture):
    """Group reads answer staff with data and everyone else with a plain 404."""

    def test_the_owner_lecturer_reads_a_group(self):
        sheet = self._marked_sheet()
        group = self._group(sheets=[sheet])
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get(reverse("assessment-group-detail", args=[group.pk]))

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["data"]["id"], str(group.pk))
        self.assertEqual(response.data["data"]["title"], "Combined")

    def test_an_admin_reads_a_group(self):
        sheet = self._marked_sheet()
        group = self._group(sheets=[sheet])
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(reverse("assessment-group-detail", args=[group.pk]))

        self.assertEqual(response.status_code, 200, response.content)

    def test_a_foreign_lecturer_gets_the_same_answer_as_a_missing_group(self):
        group = self._group(sheets=[self._marked_sheet()])
        self.client.force_authenticate(user=self.other_lecturer)

        hidden = self.client.get(reverse("assessment-group-detail", args=[group.pk]))
        absent = self.client.get(
            reverse("assessment-group-detail", args=[MISSING_UUID])
        )

        self.assertEnvelope404(hidden)
        self.assertEnvelope404(absent)
        self.assertEqual(hidden.content, absent.content)


class SheetExportTests(RouteAliasFixture):
    """One export capability, two spellings, one set of rules."""

    def test_both_export_paths_return_the_same_bytes(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        canonical = self.client.get(
            reverse("assessment-sheet-export", args=[sheet.pk])
        )
        alias = self.client.get(self._alias_export_url(sheet))

        self.assertEqual(canonical.status_code, 200, canonical.content)
        self.assertEqual(alias.status_code, 200, alias.content)
        self.assertEqual(canonical.content, alias.content)
        self.assertEqual(
            canonical["Content-Disposition"], alias["Content-Disposition"]
        )

    def test_the_response_is_a_download_with_a_safe_filename(self):
        sheet = self._marked_sheet(title="CA 1: mid/term (2026)")
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get(
            reverse("assessment-sheet-export", args=[sheet.pk])
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response["Content-Type"].startswith("text/csv"))
        disposition = response["Content-Disposition"]
        self.assertIn("attachment;", disposition)
        filename = disposition.split('filename="')[1].rstrip('"')
        self.assertTrue(filename.endswith(".csv"))
        for unsafe in ("/", "\\", ".."):
            self.assertNotIn(unsafe, filename)

    def test_the_header_is_the_pinned_column_order(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get(
            reverse("assessment-sheet-export", args=[sheet.pk])
        )

        rows = _rows(response)
        self.assertEqual(rows[0], EXPORT_COLUMNS)

    def test_every_mark_appears_with_its_student(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        rows = _rows(
            self.client.get(reverse("assessment-sheet-export", args=[sheet.pk]))
        )

        self.assertEqual(len(rows), 3)  # header + two marks
        by_student = {row[EXPORT_COLUMNS.index("student_id")]: row for row in rows[1:]}
        self.assertEqual(
            by_student[str(self.student.pk)][EXPORT_COLUMNS.index("score")], "80.00"
        )
        self.assertEqual(
            by_student[str(self.classmate.pk)][EXPORT_COLUMNS.index("score")],
            "65.00",
        )
        self.assertEqual(
            by_student[str(self.student.pk)][EXPORT_COLUMNS.index("student_name")],
            "Stu Dent",
        )

    def test_the_export_is_confined_to_its_own_offering(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        rows = _rows(
            self.client.get(reverse("assessment-sheet-export", args=[sheet.pk]))
        )

        offerings = {row[EXPORT_COLUMNS.index("course_offering_id")] for row in rows[1:]}
        self.assertEqual(offerings, {str(self.offering.pk)})

    def test_repeated_exports_of_the_same_data_are_byte_identical(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)
        url = reverse("assessment-sheet-export", args=[sheet.pk])

        first = self.client.get(url)
        second = self.client.get(url)

        self.assertEqual(first.content, second.content)

    def test_an_empty_sheet_exports_its_header_and_nothing_else(self):
        sheet = self._sheet()
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get(
            reverse("assessment-sheet-export", args=[sheet.pk])
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_rows(response), [EXPORT_COLUMNS])

    def test_commas_quotes_and_newlines_survive_the_round_trip(self):
        awkward = 'First, then "quoted", then\na second line'
        sheet = self._marked_sheet(
            rows=[{"student": str(self.student.pk), "score": "10", "comment": awkward}]
        )
        self.client.force_authenticate(user=self.lecturer)

        rows = _rows(
            self.client.get(reverse("assessment-sheet-export", args=[sheet.pk]))
        )

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][EXPORT_COLUMNS.index("comment")], awkward)

    def test_a_formula_leading_cell_is_neutralised(self):
        sheet = self._marked_sheet(
            rows=[
                {"student": str(self.student.pk), "score": "10", "comment": "=1+1"}
            ]
        )
        self.client.force_authenticate(user=self.lecturer)

        rows = _rows(
            self.client.get(reverse("assessment-sheet-export", args=[sheet.pk]))
        )

        self.assertEqual(
            rows[1][EXPORT_COLUMNS.index("comment")], "'=1+1"
        )

    def test_an_unrecorded_score_exports_as_an_empty_cell(self):
        sheet = self._marked_sheet(
            rows=[{"student": str(self.student.pk), "comment": "no show"}]
        )
        self.client.force_authenticate(user=self.lecturer)

        rows = _rows(
            self.client.get(reverse("assessment-sheet-export", args=[sheet.pk]))
        )

        self.assertEqual(rows[1][EXPORT_COLUMNS.index("score")], "")
        self.assertEqual(rows[1][EXPORT_COLUMNS.index("comment")], "no show")

    def test_the_maximum_score_is_rendered_at_its_declared_scale(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        rows = _rows(
            self.client.get(reverse("assessment-sheet-export", args=[sheet.pk]))
        )

        self.assertEqual(
            rows[1][EXPORT_COLUMNS.index("maximum_score")], "100.00"
        )


class ExportAuthorizationTests(RouteAliasFixture):
    """Who may take a file, and what they are told when they may not."""

    def test_the_owning_lecturer_may_export(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get(
            reverse("assessment-sheet-export", args=[sheet.pk])
        )

        self.assertEqual(response.status_code, 200, response.content)

    def test_an_admin_may_export(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.admin)

        response = self.client.get(
            reverse("assessment-sheet-export", args=[sheet.pk])
        )

        self.assertEqual(response.status_code, 200, response.content)

    def test_an_enrolled_student_may_not_export_a_published_sheet(self):
        """Visible to them, so a genuine 403 rather than a not-found."""
        sheet = self._marked_sheet()
        self._publish(sheet)
        self.client.force_authenticate(user=self.student)

        canonical = self.client.get(
            reverse("assessment-sheet-export", args=[sheet.pk])
        )
        alias = self.client.get(self._alias_export_url(sheet))

        for response in (canonical, alias):
            self.assertEqual(response.status_code, 403, response.content)
            self.assertFalse(response.data["success"])
            self.assertEqual(response.data["error"]["code"], "FORBIDDEN")

    def test_a_foreign_lecturer_gets_the_same_answer_as_a_missing_export(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.other_lecturer)

        hidden = self.client.get(reverse("assessment-sheet-export", args=[sheet.pk]))
        absent = self.client.get(
            reverse("assessment-sheet-export", args=[MISSING_UUID])
        )

        self.assertEnvelope404(hidden)
        self.assertEnvelope404(absent)
        self.assertEqual(hidden.content, absent.content)

    def test_an_unenrolled_student_cannot_distinguish_the_two_either(self):
        sheet = self._marked_sheet()
        self._publish(sheet)
        self.client.force_authenticate(user=self.stranger)

        hidden = self.client.get(reverse("assessment-sheet-export", args=[sheet.pk]))
        absent = self.client.get(
            reverse("assessment-sheet-export", args=[MISSING_UUID])
        )

        self.assertEnvelope404(hidden)
        self.assertEnvelope404(absent)
        self.assertEqual(hidden.content, absent.content)

    def test_a_malformed_id_is_the_same_answer_as_an_absent_one(self):
        self.client.force_authenticate(user=self.lecturer)

        malformed = self.client.get(
            reverse("assessment-sheet-export", args=[MALFORMED_ID])
        )
        absent = self.client.get(
            reverse("assessment-sheet-export", args=[MISSING_UUID])
        )
        alias_malformed = self.client.get(
            f"/api/v1/assessments/{MALFORMED_ID}/export.csv"
        )

        self.assertEnvelope404(malformed)
        self.assertEnvelope404(absent)
        self.assertEnvelope404(alias_malformed)
        self.assertEqual(malformed.content, absent.content)
        self.assertEqual(alias_malformed.content, absent.content)

    def test_an_anonymous_caller_is_refused_with_the_envelope(self):
        sheet = self._marked_sheet()
        # _marked_sheet leaves a forced lecturer session behind; drop it so the
        # request really is anonymous.
        self.client.force_authenticate(user=None)

        response = self.client.get(
            reverse("assessment-sheet-export", args=[sheet.pk])
        )

        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(response.data["success"])

    def test_a_pending_lecturer_may_not_export(self):
        sheet = self._marked_sheet()
        self.client.force_authenticate(user=self.pending_lecturer)

        response = self.client.get(
            reverse("assessment-sheet-export", args=[sheet.pk])
        )

        self.assertEnvelope404(response)


class GroupExportTests(RouteAliasFixture):
    """The group export is the same capability, widened to a group's sheets."""

    def test_the_owner_lecturer_exports_every_member_sheet(self):
        first = self._marked_sheet(title="CA 1")
        second = self._marked_sheet(title="CA 2")
        group = self._group(sheets=[first, second])
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get(
            reverse("assessment-group-export", args=[group.pk])
        )

        self.assertEqual(response.status_code, 200, response.content)
        rows = _rows(response)
        self.assertEqual(rows[0], EXPORT_COLUMNS)
        sheets = {row[EXPORT_COLUMNS.index("sheet_id")] for row in rows[1:]}
        self.assertEqual(sheets, {str(first.pk), str(second.pk)})

    def test_the_export_is_confined_to_the_groups_own_offering(self):
        first = self._marked_sheet(title="CA 1")
        group = self._group(sheets=[first])
        # Reach past the service, which would refuse this, to prove the export
        # itself is scoped: a sheet from another offering must not leak in.
        foreign_sheet = AssessmentSheet.objects.create(
            course_offering=self.other_offering,
            title="Foreign",
            category="CA",
            created_by=self.other_lecturer,
        )
        AssessmentMark.objects.create(
            assessment=foreign_sheet,
            student=self.stranger,
            score="1",
            created_by=self.other_lecturer,
        )
        group.sheets.add(foreign_sheet)
        self.client.force_authenticate(user=self.lecturer)

        rows = _rows(
            self.client.get(reverse("assessment-group-export", args=[group.pk]))
        )

        offerings = {
            row[EXPORT_COLUMNS.index("course_offering_id")] for row in rows[1:]
        }
        self.assertEqual(offerings, {str(self.offering.pk)})

    def test_a_student_is_refused_the_group_export(self):
        group = self._group(sheets=[self._marked_sheet()])
        self.client.force_authenticate(user=self.student)

        response = self.client.get(
            reverse("assessment-group-export", args=[group.pk])
        )

        self.assertIn(response.status_code, (401, 403))
        self.assertFalse(response.data["success"])

    def test_a_foreign_lecturer_gets_the_same_answer_as_a_missing_group(self):
        group = self._group(sheets=[self._marked_sheet()])
        self.client.force_authenticate(user=self.other_lecturer)

        hidden = self.client.get(reverse("assessment-group-export", args=[group.pk]))
        absent = self.client.get(
            reverse("assessment-group-export", args=[MISSING_UUID])
        )

        self.assertEnvelope404(hidden)
        self.assertEnvelope404(absent)
        self.assertEqual(hidden.content, absent.content)

    def test_a_malformed_group_id_fails_closed(self):
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get(
            reverse("assessment-group-export", args=[MALFORMED_ID])
        )

        self.assertEnvelope404(response)

    def test_a_group_with_no_sheets_exports_its_header(self):
        group = self._group(sheets=[])
        self.client.force_authenticate(user=self.lecturer)

        response = self.client.get(
            reverse("assessment-group-export", args=[group.pk])
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(_rows(response), [EXPORT_COLUMNS])


class ExportServiceContractTests(RouteAliasFixture):
    """The service function itself, outside HTTP."""

    def test_the_payload_names_its_file_and_type(self):
        sheet = self._marked_sheet()

        payload = service.export_sheet_marks_csv(
            user=self.lecturer, sheet_id=sheet.pk
        )

        self.assertEqual(payload["content_type"], "text/csv; charset=utf-8")
        self.assertTrue(payload["filename"].endswith(".csv"))
        self.assertNotIn("/", payload["filename"])
        self.assertNotIn("\\", payload["filename"])
        self.assertTrue(payload["content"].startswith(",".join(EXPORT_COLUMNS)))

    def test_the_group_payload_is_produced_by_the_same_renderer(self):
        sheet = self._marked_sheet()
        group = self._group(sheets=[sheet])

        sheet_payload = service.export_sheet_marks_csv(
            user=self.lecturer, sheet_id=sheet.pk
        )
        group_payload = service.export_group_marks_csv(
            user=self.lecturer, group_id=group.pk
        )

        self.assertEqual(sheet_payload["content"], group_payload["content"])
