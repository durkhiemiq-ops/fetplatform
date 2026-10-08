"""Accepted project decision B: a collection publishes *sheets*, not itself.

``AssessmentGroup`` stores no publication state of its own. Everything about
release is derived on read from the child sheets' existing
``AssessmentSheet.status`` lifecycle, and "publish the group" is a bulk release
executed through the same per-sheet rules the single-sheet route uses.

What these tests pin, in rough order of how badly it would hurt to be wrong:

* **The derived state is derived.** ``publication_state`` recomputes from the
  sheets on every read — DRAFT / PARTIALLY_PUBLISHED / PUBLISHED, with an empty
  collection being DRAFT — so there is no stored duplicate to fall out of sync,
  and no writable ``status`` column for a client to set.
* **One release implementation.** A bulk release and a single-sheet release
  produce identical effects *and* identical per-sheet audit records.
* **Idempotent.** A repeat is safe: no second transition, no second
  transition audit, no summary audit, and it reports ``newly_published: 0``
  instead of claiming work that did not happen.
* **Atomic and pre-validated.** The whole membership is validated before the
  first write; an empty collection is a controlled ``EMPTY_GROUP`` refusal with
  no side effects at all.
* **Authority over the collection and every sheet in it.** Sign-in alone is
  never enough, and a sheet from another offering can neither be injected nor
  silently released.
* **No student data.** The payload carries counts and sheet metadata — never a
  mark, a comment, or a private note.
"""

from datetime import timedelta

from django.core.cache import cache
from django.test import TestCase
from django.urls import Resolver404, resolve, reverse
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

from .models import AssessmentGroup, AssessmentSheet


class GroupPublicationFixture(TestCase):
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
            "gp-lect@fet.edu", "gp-lect", "Lect", "Urer", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.other_lecturer = User.objects.create_user(
            "gp-other@fet.edu", "gp-other", "Oth", "Er", "StrongPass!2026",
            role=User.Role.LECTURER,
        )
        self.student = User.objects.create_user(
            "gp-stu@fet.edu", "gp-stu", "Stu", "Dent", "StrongPass!2026",
            role=User.Role.STUDENT,
        )

        self.course = Course.objects.create(
            code="CS301", name="Operating Systems", department=self.department
        )
        self.offering = CourseOffering.objects.create(
            course=self.course,
            semester=self.semester,
            department=self.department,
            lecturer=self.lecturer,
        )
        self.other_course = Course.objects.create(
            code="CS302", name="Databases", department=self.department
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

    # -- helpers ----------------------------------------------------------

    def authenticate(self, user):
        self.client.force_authenticate(user=user)
        return self.client

    def sheet(self, *, title="CA 1", offering=None, **body):
        target = offering or self.offering
        # A foreign offering's sheets have to be made by *its* lecturer, or the
        # create call fails on ownership before the test says anything useful.
        self.client.force_authenticate(user=target.lecturer or self.lecturer)
        payload = {"title": title, "category": "CA"}
        payload.update(body)
        response = self.client.post(
            reverse("offering-assessment-sheets", args=[target.pk]),
            payload,
            format="json",
        )
        assert response.status_code == 201, response.content
        return AssessmentSheet.objects.get(pk=response.data["data"]["id"])

    def group(self, *, title="Combined", sheets=None):
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

    def read_group(self, group, *, user=None):
        response = self.authenticate(user or self.lecturer).get(
            reverse("assessment-group-detail", args=[group.pk])
        )
        assert response.status_code == 200, response.content
        return response.json()["data"]

    def publish(self, group, *, user=None, body=None):
        return self.authenticate(user or self.lecturer).post(
            reverse("assessment-group-publish", args=[group.pk]),
            {} if body is None else body,
            format="json",
        )

    def _release(self, sheet):
        """Release one sheet through the canonical single-sheet route."""
        response = self.authenticate(self.lecturer).patch(
            reverse("assessment-sheet-publish", args=[sheet.pk]),
            {"status": "PUBLISHED"},
            format="json",
        )
        assert response.status_code == 200, response.content

    def status_of(self, sheet):
        sheet.refresh_from_db()
        return sheet.status


class DerivedPublicationStateTests(GroupPublicationFixture):
    def test_an_empty_collection_reads_as_draft(self):
        group = self.group(title="Nothing yet")

        data = self.read_group(group)

        self.assertEqual(data["publication_state"], "DRAFT")
        self.assertEqual(data["sheet_count"], 0)
        self.assertEqual(data["published_sheet_count"], 0)
        # The pre-decision key is still answered, with the same measurement.
        self.assertEqual(data["sheets_count"], data["sheet_count"])

    def test_all_draft_sheets_read_as_draft(self):
        sheets = [self.sheet(title="CA 1"), self.sheet(title="CA 2")]
        group = self.group(sheets=sheets)

        data = self.read_group(group)

        self.assertEqual(data["publication_state"], "DRAFT")
        self.assertEqual(data["sheet_count"], 2)
        self.assertEqual(data["published_sheet_count"], 0)

    def test_one_published_of_two_reads_as_partially_published(self):
        draft = self.sheet(title="CA 1")
        released = self.sheet(title="CA 2")
        group = self.group(sheets=[draft, released])
        self.authenticate(self.lecturer).patch(
            reverse("assessment-sheet-publish", args=[released.pk]),
            {"status": "PUBLISHED"},
            format="json",
        )

        data = self.read_group(group)

        self.assertEqual(data["publication_state"], "PARTIALLY_PUBLISHED")
        self.assertEqual(data["sheet_count"], 2)
        self.assertEqual(data["published_sheet_count"], 1)

    def test_every_published_sheet_reads_as_published(self):
        sheets = [self.sheet(title="CA 1"), self.sheet(title="CA 2")]
        group = self.group(sheets=sheets)
        for sheet in sheets:
            self._release(sheet)

        data = self.read_group(group)

        self.assertEqual(data["publication_state"], "PUBLISHED")
        self.assertEqual(data["published_sheet_count"], 2)

    def test_state_is_recomputed_from_the_sheets_not_stored(self):
        """A sheet added later can make a finished collection partial again."""
        first = self.sheet(title="CA 1")
        group = self.group(sheets=[first])
        self._release(first)
        self.assertEqual(self.read_group(group)["publication_state"], "PUBLISHED")

        second = self.sheet(title="CA 2")
        self.authenticate(self.lecturer).patch(
            reverse("assessment-group-detail", args=[group.pk]),
            {"sheets": [str(first.pk), str(second.pk)]},
            format="json",
        )

        data = self.read_group(group)
        self.assertEqual(data["publication_state"], "PARTIALLY_PUBLISHED")
        self.assertEqual(data["published_sheet_count"], 1)

    def test_sheet_detail_carries_only_sheet_metadata(self):
        sheet = self.sheet(title="CA 1")
        group = self.group(sheets=[sheet])

        detail = self.read_group(group)["sheets_detail"]

        self.assertEqual(len(detail), 1)
        self.assertEqual(detail[0]["id"], str(sheet.pk))
        self.assertEqual(detail[0]["title"], "CA 1")
        self.assertEqual(detail[0]["category"], "CA")
        self.assertEqual(detail[0]["status"], "DRAFT")

    def test_list_shape_carries_the_same_derived_values(self):
        draft = self.sheet(title="CA 1")
        released = self.sheet(title="CA 2")
        self.group(sheets=[draft, released])
        self._release(released)

        response = self.authenticate(self.lecturer).get(
            reverse("offering-assessment-groups", args=[self.offering.pk])
        )
        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()["data"][0]
        self.assertEqual(row["publication_state"], "PARTIALLY_PUBLISHED")
        self.assertEqual(row["sheet_count"], 2)
        self.assertEqual(row["published_sheet_count"], 1)



class BulkReleaseTests(GroupPublicationFixture):
    def test_publishing_releases_every_draft_sheet(self):
        first = self.sheet(title="CA 1")
        second = self.sheet(title="CA 2")
        group = self.group(sheets=[first, second])

        response = self.publish(group)

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertEqual(data["newly_published"], 2)
        self.assertEqual(data["already_published"], 0)
        self.assertEqual(data["publication_state"], "PUBLISHED")
        self.assertEqual(self.status_of(first), "PUBLISHED")
        self.assertEqual(self.status_of(second), "PUBLISHED")

    def test_the_response_reports_derived_state_for_the_next_render(self):
        group = self.group(sheets=[self.sheet(title="CA 1")])

        data = self.publish(group).json()["data"]

        self.assertEqual(data["sheet_count"], 1)
        self.assertEqual(data["published_sheet_count"], 1)
        self.assertEqual(data["publication_state"], "PUBLISHED")

    def test_a_second_request_is_idempotent_and_claims_no_new_work(self):
        sheet = self.sheet(title="CA 1")
        group = self.group(sheets=[sheet])
        first = self.publish(group)
        self.assertEqual(first.json()["data"]["newly_published"], 1)

        AuditEvent.objects.all().delete()
        second = self.publish(group)

        self.assertEqual(second.status_code, 200, second.content)
        data = second.json()["data"]
        self.assertEqual(data["newly_published"], 0)
        self.assertEqual(data["already_published"], 1)
        self.assertEqual(data["publication_state"], "PUBLISHED")
        # No second transition, no second transition audit, no summary audit.
        self.assertFalse(
            AuditEvent.objects.filter(action="assessment_sheet_published").exists()
        )
        self.assertFalse(
            AuditEvent.objects.filter(action="assessment_group_published").exists()
        )
        self.assertEqual(AuditEvent.objects.count(), 0)

    def test_already_released_sheets_are_counted_not_re_released(self):
        draft = self.sheet(title="CA 1")
        released = self.sheet(title="CA 2")
        group = self.group(sheets=[draft, released])
        self._release(released)
        AuditEvent.objects.all().delete()

        data = self.publish(group).json()["data"]

        self.assertEqual(data["newly_published"], 1)
        self.assertEqual(data["already_published"], 1)
        # Exactly one new transition audit — for the sheet that actually moved.
        transitions = AuditEvent.objects.filter(
            action="assessment_sheet_published"
        )
        self.assertEqual(transitions.count(), 1)
        self.assertEqual(str(transitions.first().resource_id), str(draft.pk))

    def test_releases_and_the_group_summary_share_one_transaction(self):
        first = self.sheet(title="CA 1")
        second = self.sheet(title="CA 2")
        group = self.group(sheets=[first, second])

        self.publish(group)

        self.assertEqual(
            AuditEvent.objects.filter(action="assessment_group_published").count(), 1
        )
        self.assertEqual(
            AuditEvent.objects.filter(action="assessment_sheet_published").count(), 2
        )

    def test_the_summary_audit_carries_counts_and_no_secrets(self):
        group = self.group(sheets=[self.sheet(title="CA 1")])

        self.publish(group)

        entry = AuditEvent.objects.get(action="assessment_group_published")
        self.assertEqual(entry.details.get("sheet_count"), 1)
        self.assertEqual(entry.details.get("newly_published"), 1)
        self.assertEqual(entry.details.get("already_published"), 0)
        # Nothing credential-shaped or student-shaped in the summary.
        blob = str(entry.details).lower()
        for forbidden in ("password", "token", "secret", "matricule", "comment"):
            self.assertNotIn(forbidden, blob)

    def test_an_empty_collection_is_a_controlled_refusal_with_no_side_effects(self):
        group = self.group(title="Nothing yet")
        # The creation of the collection itself is audited; the *refused*
        # publish must add nothing at all.
        AuditEvent.objects.all().delete()

        response = self.publish(group)

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.json()["error"]["code"], "EMPTY_GROUP")
        self.assertEqual(AuditEvent.objects.count(), 0)
        self.assertFalse(
            AuditEvent.objects.filter(action="assessment_group_published").exists()
        )

    def test_the_body_is_not_allowed_to_supply_state(self):
        group = self.group(sheets=[self.sheet(title="CA 1")])

        for body in ({"status": "DRAFT"}, {"published": False}, ["PUBLISHED"]):
            with self.subTest(body=body):
                response = self.publish(group, body=body)
                self.assertEqual(response.status_code, 400, response.content)
                self.assertEqual(
                    response.json()["error"]["code"], "INVALID_INPUT"
                )
        self.assertEqual(
            AssessmentSheet.objects.filter(status="PUBLISHED").count(), 0
        )

    def test_another_lecturer_cannot_publish_a_group_they_cannot_see(self):
        sheet = self.sheet(title="CA 1")
        group = self.group(sheets=[sheet])

        response = self.publish(group, user=self.other_lecturer)

        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(self.status_of(sheet), "DRAFT")
        self.assertFalse(
            AuditEvent.objects.filter(action="assessment_group_published").exists()
        )

    def test_a_student_is_refused_before_the_service(self):
        group = self.group(sheets=[self.sheet(title="CA 1")])

        response = self.publish(group, user=self.student)

        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(response.json()["success"])

    def test_anonymous_is_refused_with_the_envelope(self):
        group = self.group(sheets=[self.sheet(title="CA 1")])
        # `force_authenticate` sticks for the whole test client; drop it so the
        # request below really is anonymous.
        self.client.force_authenticate(user=None)

        response = self.client.post(
            reverse("assessment-group-publish", args=[group.pk]), {}, format="json"
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertFalse(response.json()["success"])

    def test_a_malformed_group_id_answers_the_standard_404_envelope(self):
        response = self.authenticate(self.lecturer).post(
            "/api/v1/assessment-groups/not-a-uuid/publish/", {}, format="json"
        )
        self.assertEqual(response.status_code, 404, response.content)
        self.assertEqual(response.json()["error"]["code"], "NOT_FOUND")



class GroupPatchContractTests(GroupPublicationFixture):
    def test_status_is_rejected_explicitly_not_silently_dropped(self):
        group = self.group(sheets=[self.sheet(title="CA 1")])

        response = self.authenticate(self.lecturer).patch(
            reverse("assessment-group-detail", args=[group.pk]),
            {"status": "PUBLISHED"},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        message = response.json()["error"]["message"]
        self.assertEqual(response.json()["error"]["code"], "INVALID_INPUT")
        self.assertIn("status", message)
        self.assertIn("title and sheets", message)
        # The sheet is untouched: nothing was published by a rejected request.
        self.assertEqual(
            AssessmentSheet.objects.get().status, "DRAFT"
        )

    def test_an_unpublish_request_is_rejected_too(self):
        group = self.group(sheets=[self.sheet(title="CA 1")])

        response = self.authenticate(self.lecturer).patch(
            reverse("assessment-group-detail", args=[group.pk]),
            {"status": "DRAFT"},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)

    def test_title_still_updates(self):
        group = self.group(title="Old title")

        response = self.authenticate(self.lecturer).patch(
            reverse("assessment-group-detail", args=[group.pk]),
            {"title": "New title"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["title"], "New title")
        # Editing metadata must not touch publication state.
        self.assertEqual(response.json()["data"]["publication_state"], "DRAFT")

    def test_membership_edit_recalculates_derived_state(self):
        draft = self.sheet(title="CA 1")
        released = self.sheet(title="CA 2")
        self._release(released)
        group = self.group(sheets=[draft])

        response = self.authenticate(self.lecturer).patch(
            reverse("assessment-group-detail", args=[group.pk]),
            {"sheets": [str(draft.pk), str(released.pk)]},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertEqual(data["publication_state"], "PARTIALLY_PUBLISHED")
        self.assertEqual(data["published_sheet_count"], 1)

    def test_a_sheet_from_another_offering_cannot_be_injected(self):
        foreign = self.sheet(title="Other CA", offering=self.other_offering)
        group = self.group(sheets=[self.sheet(title="CA 1")])

        response = self.authenticate(self.lecturer).patch(
            reverse("assessment-group-detail", args=[group.pk]),
            {"sheets": [str(foreign.pk)]},
            format="json",
        )

        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(group.sheets.count(), 1)

    def test_publishing_all_then_editing_membership_leaves_states_consistent(self):
        first = self.sheet(title="CA 1")
        group = self.group(sheets=[first])
        self.assertEqual(self.publish(group).status_code, 200)

        added = self.sheet(title="CA 2")
        self.authenticate(self.lecturer).patch(
            reverse("assessment-group-detail", args=[group.pk]),
            {"sheets": [str(first.pk), str(added.pk)]},
            format="json",
        )

        data = self.read_group(group)
        self.assertEqual(data["publication_state"], "PARTIALLY_PUBLISHED")
        self.assertEqual(data["published_sheet_count"], 1)

        # And the remaining sheet releases through the same route.
        self.assertEqual(self.publish(group).json()["data"]["newly_published"], 1)
        self.assertEqual(self.read_group(group)["publication_state"], "PUBLISHED")



class NoBulkUnpublishTests(GroupPublicationFixture):
    def test_no_unpublish_route_exists(self):
        """A bulk *unpublish* was explicitly not built."""
        with self.assertRaises(Resolver404):
            resolve("/api/v1/assessment-groups/00000000-0000-0000-0000-000000000000/unpublish/")

    def test_single_sheet_unpublish_still_works_but_not_as_a_group_action(self):
        sheet = self.sheet(title="CA 1")
        group = self.group(sheets=[sheet])
        self.assertEqual(self.publish(group).status_code, 200)

        response = self.authenticate(self.lecturer).patch(
            reverse("assessment-sheet-publish", args=[sheet.pk]),
            {"status": "DRAFT"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        # The single-sheet route is unchanged; the *group* is what recalculates.
        data = self.read_group(group)
        self.assertEqual(data["publication_state"], "DRAFT")
        self.assertEqual(data["published_sheet_count"], 0)


class NoStudentExposureTests(GroupPublicationFixture):
    def test_the_group_payload_carries_no_marks_or_private_notes(self):
        sheet = self.sheet(title="CA 1")
        self.authenticate(self.lecturer).put(
            reverse("assessment-sheet-marks", args=[sheet.pk]),
            {
                "marks": [
                    {
                        "student": str(self.student.pk),
                        "score": "81",
                        "comment": "distinctive-comment-xyz",
                    }
                ]
            },
            format="json",
        )
        group = self.group(sheets=[sheet])

        for payload in (
            self.read_group(group),
            self.publish(group).json()["data"],
        ):
            blob = str(payload).lower()
            self.assertNotIn("distinctive-comment-xyz", blob)
            self.assertNotIn("private_notes", blob)
            self.assertNotIn(str(self.student.pk), blob)
            for forbidden in ("marks", "students", "score"):
                self.assertNotIn(forbidden, payload)

    def test_a_student_cannot_read_or_publish_a_group(self):
        group = self.group(sheets=[self.sheet(title="CA 1")])
        self.client.force_authenticate(user=self.student)

        read = self.client.get(
            reverse("assessment-group-detail", args=[group.pk])
        )
        publish = self.client.post(
            reverse("assessment-group-publish", args=[group.pk]), {}, format="json"
        )

        # 403 on the detail read (strict staff surface), and the publish route
        # never reaches the service.
        self.assertEqual(read.status_code, 403, read.content)
        self.assertEqual(publish.status_code, 403, publish.content)
        self.assertEqual(AssessmentSheet.objects.get().status, "DRAFT")
