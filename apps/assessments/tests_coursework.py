"""Coursework surface tests: contract, ownership, and the student dispute path.

This module covers the coursework API that was inferred from the client (see
``models.py`` for why it is inferred rather than specified). Because no spec
defines it, the tests are the only thing pinning the contract, so they lean
hard on the properties that would hurt most if they were wrong:

* **Ownership.** Only the lecturer who teaches an offering may write to it.
  Another lecturer gets the same answer as a nonexistent offering id, so the
  route cannot be used to discover which offerings exist (§25).
* **The approval gate.** A lecturer whose application is still PENDING is
  refused even though their role says LECTURER. Role alone is not authority.
* **Student reads.** A student sees the coursework of their own enrolled
  offerings — and *only* those — including their own submission and their own
  mark, never another student's.
* **Students cannot grade.** Neither their own work nor anyone else's, and
  they cannot move their own score or close their own dispute.
* **Attempts.** ``max_submissions`` is enforced, and work returned for
  revision can be handed in again.
* **Denial shape.** Every refusal answers with the project envelope, and the
  not-found and not-permitted cases are byte-identical where §25 requires it.
"""

from datetime import timedelta

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
from core.models import AuditEvent

from .models import AssessmentMark, AssessmentSheet, Assignment

MISSING_UUID = "00000000-0000-0000-0000-000000000000"


class CourseworkFixture(TestCase):
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
            "cw-lect@fet.edu", "cw-lect", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.other_lecturer = User.objects.create_user(
            "cw-other-lect@fet.edu", "cw-other-lect", "Oth", "Er", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        # A lecturer who signed themselves up and has not been approved yet.
        self.pending_lecturer = User.objects.create_user(
            "cw-pending@fet.edu", "cw-pending", "Pen", "Ding", "StrongPass!2026",
            role=User.Role.LECTURER,
            lecturer_approval_status=User.LecturerApproval.PENDING,
        )
        self.admin = User.objects.create_user(
            "cw-admin@fet.edu", "cw-admin", "Ad", "Min", "StrongPass!2026",
            role=User.Role.ADMINISTRATOR,
        )
        self.student = User.objects.create_user(
            "cw-stu@fet.edu", "cw-stu", "Stu", "Dent", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.classmate = User.objects.create_user(
            "cw-mate@fet.edu", "cw-mate", "Mat", "E", "StrongPass!2026",
            role=User.Role.STUDENT,
        )
        self.stranger = User.objects.create_user(
            "cw-stranger@fet.edu", "cw-stranger", "Str", "Ange", "StrongPass!2026",
            role=User.Role.STUDENT,
        )

        self.course = Course.objects.create(
            code="CS301", name="Operating Systems", department=self.department
        )
        self.other_course = Course.objects.create(
            code="CS302", name="Databases", department=self.department
        )
        self.offering = CourseOffering.objects.create(
            course=self.course,
            semester=self.semester,
            department=self.department,
            lecturer=self.lecturer,
        )
        self.other_offering = CourseOffering.objects.create(
            course=self.other_course,
            semester=self.semester,
            department=self.department,
            lecturer=self.other_lecturer,
        )

        Enrollment.objects.create(
            student=self.student, course=self.course, course_offering=self.offering
        )
        Enrollment.objects.create(
            student=self.classmate, course=self.course, course_offering=self.offering
        )
        Enrollment.objects.create(
            student=self.stranger,
            course=self.other_course,
            course_offering=self.other_offering,
        )

    # -- helpers -----------------------------------------------------------

    def _assignments_url(self, offering=None):
        return reverse("offering-assignments", args=[(offering or self.offering).pk])

    def _create_assignment(self, *, user=None, offering=None, **body):
        self.client.force_authenticate(user=user or self.lecturer)
        payload = {"title": "Essay 1"}
        payload.update(body)
        return self.client.post(self._assignments_url(offering), payload, format="json")

    def _assignment(self, *, user=None, offering=None, **body):
        response = self._create_assignment(user=user, offering=offering, **body)
        assert response.status_code == 201, response.content
        return Assignment.objects.get(pk=response.data["data"]["id"])

    def _sheet(self, *, title="CA 1", **body):
        self.client.force_authenticate(user=self.lecturer)
        payload = {"title": title, "category": "CA", "maximum_score": "100", "weight": "30"}
        payload.update(body)
        response = self.client.post(
            reverse("offering-assessment-sheets", args=[self.offering.pk]),
            payload,
            format="json",
        )
        assert response.status_code == 201, response.content
        return AssessmentSheet.objects.get(pk=response.data["data"]["id"])

    def _publish(self, sheet):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.patch(
            reverse("assessment-sheet-publish", args=[sheet.pk]),
            {"status": "PUBLISHED"},
            format="json",
        )
        assert response.status_code == 200, response.content
        return response


class AssignmentAccessTests(CourseworkFixture):
    def test_anonymous_create_is_refused_with_the_envelope(self):
        response = self.client.post(self._assignments_url(), {"title": "x"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])
        self.assertIn("error", response.data)

    def test_student_cannot_create_an_assignment(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.post(self._assignments_url(), {"title": "x"}, format="json")
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])

    def test_owner_lecturer_creates_and_it_is_audited(self):
        response = self._create_assignment(
            description="Read chapter 4",
            due_at=(timezone.now() + timedelta(days=7)).isoformat(),
            allow_late=True,
            max_submissions=3,
        )
        self.assertEqual(response.status_code, 201, response.content)
        data = response.data["data"]
        self.assertEqual(data["title"], "Essay 1")
        self.assertEqual(data["max_submissions"], 3)
        self.assertTrue(data["allow_late"])
        self.assertTrue(
            AuditEvent.objects.filter(
                action="assignment_created", resource_type="assignment"
            ).exists()
        )

    def test_another_lecturer_cannot_write_to_this_offering(self):
        response = self._create_assignment(user=self.other_lecturer)
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])
        self.assertEqual(response.data["error"]["code"], "NOT_FOUND")

    def test_forbidden_and_unknown_offering_ids_answer_identically(self):
        # §25: a lecturer who does not teach this offering must not be able to
        # tell it apart from one that was never created.
        known = self._create_assignment(user=self.other_lecturer)
        self.client.force_authenticate(user=self.other_lecturer)
        missing = self.client.post(
            reverse("offering-assignments", args=[MISSING_UUID]),
            {"title": "Essay 1"},
            format="json",
        )
        self.assertEqual(known.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(known.content, missing.content)
        self.assertEqual(Assignment.objects.count(), 0)

    def test_unapproved_lecturer_is_refused_despite_the_role(self):
        # Writing is refused by the permission class...
        response = self._create_assignment(user=self.pending_lecturer)
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])
        # ...and reading is refused by the scope, which is what keeps a
        # PENDING applicant from enumerating offerings by role alone.
        self.client.force_authenticate(user=self.pending_lecturer)
        listing = self.client.get(self._assignments_url())
        self.assertEqual(listing.status_code, 404)
        self.assertFalse(listing.data["success"])

    def test_administrator_may_write_to_any_offering(self):
        response = self._create_assignment(user=self.admin)
        self.assertEqual(response.status_code, 201, response.content)

    def test_enrolled_student_lists_assignments_with_their_own_slot(self):
        self._assignment(title="Essay 1")
        self.client.force_authenticate(user=self.student)
        response = self.client.get(self._assignments_url())
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["title"], "Essay 1")
        # The client renders the student's own attempt from this key.
        self.assertIn("my_submission", rows[0])
        self.assertIsNone(rows[0]["my_submission"])

    def test_student_sees_nothing_for_an_offering_they_are_not_on(self):
        self.client.force_authenticate(user=self.stranger)
        response = self.client.get(self._assignments_url())
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])


class SubmissionTests(CourseworkFixture):
    def _submit(self, user, assignment, payload=None):
        self.client.force_authenticate(user=user)
        return self.client.post(
            reverse("assignment-submissions", args=[assignment.pk]),
            payload or {"note": "here is my work"},
            format="json",
        )

    def test_enrolled_student_submits_work_and_it_is_audited(self):
        assignment = self._assignment()
        response = self._submit(self.student, assignment)
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.data["data"]["status"], "SUBMITTED")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="assignment_submitted", resource_type="submission"
            ).exists()
        )

    def test_second_attempt_is_refused_once_the_limit_is_reached(self):
        assignment = self._assignment()  # max_submissions defaults to 1
        self.assertEqual(self._submit(self.student, assignment).status_code, 201)
        second = self._submit(self.student, assignment)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.data["error"]["code"], "SUBMISSION_LIMIT")

    def test_work_returned_for_revision_can_be_handed_in_again(self):
        assignment = self._assignment()
        self._submit(self.student, assignment)

        submission = assignment.submissions.get(student=self.student)
        self.client.force_authenticate(user=self.lecturer)
        graded = self.client.patch(
            reverse("submission-detail", args=[submission.pk]),
            {"status": "RETURNED", "feedback": "add a conclusion"},
            format="json",
        )
        self.assertEqual(graded.status_code, 200, graded.content)
        self.assertEqual(graded.data["data"]["status"], "RETURNED")

        # Returning work is an invitation to resubmit, so it does not count
        # against the one permitted attempt.
        again = self._submit(self.student, assignment)
        self.assertEqual(again.status_code, 201, again.content)

    def test_late_submission_is_refused_when_late_is_not_allowed(self):
        assignment = self._assignment(
            due_at=(timezone.now() - timedelta(days=2)).isoformat(),
            allow_late=False,
        )
        response = self._submit(self.student, assignment)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "INVALID_INPUT")

    def test_unenrolled_student_gets_the_same_answer_as_a_missing_assignment(self):
        # §25: probing a real assignment id must not confirm it exists.
        assignment = self._assignment()
        self.client.force_authenticate(user=self.stranger)
        real = self.client.get(
            reverse("assignment-submissions", args=[assignment.pk])
        )
        missing = self.client.get(
            reverse("assignment-submissions", args=[MISSING_UUID])
        )
        self.assertEqual(real.status_code, 404)
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(real.content, missing.content)

    def test_student_cannot_grade_their_own_submission(self):
        assignment = self._assignment()
        self._submit(self.student, assignment)
        submission = assignment.submissions.get(student=self.student)

        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("submission-detail", args=[submission.pk]),
            {"grade": "A+", "status": "GRADED"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])
        submission.refresh_from_db()
        self.assertEqual(submission.status, "SUBMITTED")
        self.assertEqual(submission.grade, "")

    def test_another_lecturer_cannot_grade(self):
        assignment = self._assignment()
        self._submit(self.student, assignment)
        submission = assignment.submissions.get(student=self.student)

        self.client.force_authenticate(user=self.other_lecturer)
        response = self.client.patch(
            reverse("submission-detail", args=[submission.pk]),
            {"grade": "A", "status": "GRADED"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        submission.refresh_from_db()
        self.assertEqual(submission.status, "SUBMITTED")

    def test_owner_lecturer_grades_and_it_is_audited(self):
        assignment = self._assignment()
        self._submit(self.student, assignment)
        submission = assignment.submissions.get(student=self.student)

        self.client.force_authenticate(user=self.lecturer)
        response = self.client.patch(
            reverse("submission-detail", args=[submission.pk]),
            {"grade": "B+", "feedback": "solid", "status": "GRADED"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["data"]["status"], "GRADED")
        self.assertEqual(response.data["data"]["grade"], "B+")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="submission_graded", resource_type="submission"
            ).exists()
        )

    def test_submission_list_is_scoped_to_the_calling_student(self):
        assignment = self._assignment()
        self._submit(self.student, assignment)

        self.client.force_authenticate(user=self.classmate)
        response = self.client.get(reverse("assignment-submissions", args=[assignment.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        # A classmate must not receive the other student's work.
        self.assertEqual(response.data["data"], [])

        # The author does see their own row.
        self.client.force_authenticate(user=self.student)
        own = self.client.get(reverse("assignment-submissions", args=[assignment.pk]))
        self.assertEqual(len(own.data["data"]), 1)
        self.assertEqual(own.data["data"][0]["student"], str(self.student.pk))


class SheetAndMarkTests(CourseworkFixture):
    def _save_marks(self, sheet, rows, user=None):
        self.client.force_authenticate(user=user or self.lecturer)
        return self.client.put(
            reverse("assessment-sheet-marks", args=[sheet.pk]),
            {"marks": rows},
            format="json",
        )

    def test_student_sees_only_published_sheets(self):
        draft = self._sheet(title="Draft CA")
        released = self._sheet(title="Released CA")
        self._publish(released)

        self.client.force_authenticate(user=self.student)
        response = self.client.get(
            reverse("offering-assessment-sheets", args=[self.offering.pk])
        )
        self.assertEqual(response.status_code, 200, response.content)
        titles = [row["title"] for row in response.data["data"]]
        self.assertEqual(titles, ["Released CA"])
        self.assertNotIn(str(draft.pk), [str(r["id"]) for r in response.data["data"]])

    def test_marks_save_is_an_upsert_rather_than_a_duplicate(self):
        sheet = self._sheet()
        row = {"student": str(self.student.pk), "score": "72.50", "comment": "ok"}
        first = self._save_marks(sheet, [row])
        self.assertEqual(first.status_code, 200, first.content)
        self.assertEqual(AssessmentMark.objects.filter(assessment=sheet).count(), 1)

        second = self._save_marks(sheet, [dict(row, score="80.00")])
        self.assertEqual(second.status_code, 200, second.content)
        self.assertEqual(AssessmentMark.objects.filter(assessment=sheet).count(), 1)
        mark = AssessmentMark.objects.get(assessment=sheet)
        self.assertEqual(str(mark.score), "80.00")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="assessment_marks_saved", resource_type="assessment_sheet"
            ).exists()
        )

    def test_score_above_the_maximum_is_refused(self):
        sheet = self._sheet(maximum_score="50")
        response = self._save_marks(
            sheet, [{"student": str(self.student.pk), "score": "90"}]
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "INVALID_INPUT")
        self.assertEqual(AssessmentMark.objects.filter(assessment=sheet).count(), 0)

    def test_lowering_the_maximum_below_a_recorded_mark_is_refused(self):
        sheet = self._sheet()
        self._save_marks(sheet, [{"student": str(self.student.pk), "score": "90"}])

        self.client.force_authenticate(user=self.lecturer)
        response = self.client.patch(
            reverse("assessment-sheet-detail", args=[sheet.pk]),
            {"maximum_score": "50"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        sheet.refresh_from_db()
        # The ceiling was not quietly lowered underneath the mark already in.
        self.assertEqual(str(sheet.maximum_score), "100.00")

    def test_student_reads_only_their_own_mark_on_a_published_sheet(self):
        sheet = self._sheet()
        self._save_marks(
            sheet,
            [
                {"student": str(self.student.pk), "score": "70"},
                {"student": str(self.classmate.pk), "score": "55"},
            ],
        )
        self._publish(sheet)

        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("assessment-sheet-marks", args=[sheet.pk]))
        self.assertEqual(response.status_code, 200, response.content)
        marks = response.data["data"]["marks"]
        self.assertEqual(len(marks), 1)
        self.assertEqual(str(marks[0]["score"]), "70.00")
        # No trace of the classmate's mark arrives on this path.
        self.assertNotIn(str(self.classmate.pk), str(response.data))

    def test_student_cannot_read_a_draft_sheet(self):
        sheet = self._sheet()
        self._save_marks(sheet, [{"student": str(self.student.pk), "score": "70"}])

        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("assessment-sheet-marks", args=[sheet.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])

    def test_student_can_raise_a_dispute_about_their_own_released_mark(self):
        sheet = self._sheet()
        self._save_marks(sheet, [{"student": str(self.student.pk), "score": "40"}])
        self._publish(sheet)
        mark = AssessmentMark.objects.get(assessment=sheet, student=self.student)

        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("assessment-mark-detail", args=[mark.pk]),
            {"dispute_reason": "Question 3 was marked out of 10, not 20."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.data["data"]["dispute_status"], "OPEN")
        mark.refresh_from_db()
        self.assertEqual(mark.dispute_status, "OPEN")
        self.assertTrue(
            AuditEvent.objects.filter(
                action="assessment_mark_updated", resource_type="assessment_mark"
            ).exists()
        )

    def test_student_cannot_move_their_own_score(self):
        sheet = self._sheet()
        self._save_marks(sheet, [{"student": str(self.student.pk), "score": "40"}])
        self._publish(sheet)
        mark = AssessmentMark.objects.get(assessment=sheet, student=self.student)

        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("assessment-mark-detail", args=[mark.pk]),
            {"score": "100"},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.data["error"]["code"], "FORBIDDEN")
        mark.refresh_from_db()
        self.assertEqual(str(mark.score), "40.00")

    def test_student_cannot_close_their_own_dispute(self):
        # Clearing the reason is what closes a dispute; if a student could do
        # it they would raise and resolve their own complaint unobserved.
        sheet = self._sheet()
        self._save_marks(sheet, [{"student": str(self.student.pk), "score": "40"}])
        self._publish(sheet)
        mark = AssessmentMark.objects.get(assessment=sheet, student=self.student)
        mark.dispute_reason = "too low"
        mark.dispute_status = "OPEN"
        mark.save()

        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("assessment-mark-detail", args=[mark.pk]),
            {"dispute_reason": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 403)
        mark.refresh_from_db()
        self.assertEqual(mark.dispute_status, "OPEN")

    def test_student_cannot_dispute_another_students_mark(self):
        sheet = self._sheet()
        self._save_marks(
            sheet,
            [
                {"student": str(self.student.pk), "score": "40"},
                {"student": str(self.classmate.pk), "score": "90"},
            ],
        )
        self._publish(sheet)
        theirs = AssessmentMark.objects.get(assessment=sheet, student=self.classmate)

        self.client.force_authenticate(user=self.student)
        response = self.client.patch(
            reverse("assessment-mark-detail", args=[theirs.pk]),
            {"dispute_reason": "not mine"},
            format="json",
        )
        # §25: reported as absent rather than forbidden, so a student cannot
        # confirm that another student's mark row exists.
        self.assertEqual(response.status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.dispute_status, "RESOLVED")

    def test_lecturer_resolves_a_dispute(self):
        sheet = self._sheet()
        self._save_marks(sheet, [{"student": str(self.student.pk), "score": "40"}])
        self._publish(sheet)
        mark = AssessmentMark.objects.get(assessment=sheet, student=self.student)
        mark.dispute_reason = "too low"
        mark.dispute_status = "OPEN"
        mark.save()

        self.client.force_authenticate(user=self.lecturer)
        response = self.client.patch(
            reverse("assessment-mark-detail", args=[mark.pk]),
            {"dispute_response": "Recounted; the total stands."},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        mark.refresh_from_db()
        self.assertEqual(mark.dispute_status, "RESOLVED")


class GroupTests(CourseworkFixture):
    def test_student_cannot_list_groups(self):
        self.client.force_authenticate(user=self.student)
        response = self.client.get(
            reverse("offering-assessment-groups", args=[self.offering.pk])
        )
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])

    def test_another_lecturer_cannot_create_a_group(self):
        self.client.force_authenticate(user=self.other_lecturer)
        response = self.client.post(
            reverse("offering-assessment-groups", args=[self.offering.pk]),
            {"title": "CA total"},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(response.data["success"])

    def test_group_lifecycle_is_audited(self):
        sheet = self._sheet()
        self.client.force_authenticate(user=self.lecturer)
        created = self.client.post(
            reverse("offering-assessment-groups", args=[self.offering.pk]),
            {"title": "CA total", "sheets": [str(sheet.pk)]},
            format="json",
        )
        self.assertEqual(created.status_code, 201, created.content)
        group_id = created.data["data"]["id"]
        self.assertTrue(
            AuditEvent.objects.filter(
                action="assessment_group_created", resource_type="assessment_group"
            ).exists()
        )

        deleted = self.client.delete(
            reverse("assessment-group-detail", args=[group_id])
        )
        self.assertEqual(deleted.status_code, 200, deleted.content)
        self.assertTrue(
            AuditEvent.objects.filter(
                action="assessment_group_deleted", resource_type="assessment_group"
            ).exists()
        )


class MyAssignmentsTests(CourseworkFixture):
    def test_student_receives_only_their_own_coursework(self):
        self._assignment(title="Essay 1")
        self._assignment(title="Essay 2", offering=self.other_offering,
                         user=self.other_lecturer)

        self.client.force_authenticate(user=self.student)
        response = self.client.get(reverse("my-assignments"))
        self.assertEqual(response.status_code, 200, response.content)
        rows = response.data["data"]["assignments"]
        self.assertEqual([r["title"] for r in rows], ["Essay 1"])
        self.assertEqual(rows[0]["course_code"], "CS301")
        self.assertIn("my_submission", rows[0])

    def test_lecturer_cannot_use_the_student_endpoint(self):
        self.client.force_authenticate(user=self.lecturer)
        response = self.client.get(reverse("my-assignments"))
        self.assertEqual(response.status_code, 403)
        self.assertFalse(response.data["success"])
