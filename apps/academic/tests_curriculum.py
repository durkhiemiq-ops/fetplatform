"""Curriculum registration: server ownership, atomicity, history and attendance."""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.db.models import QuerySet
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.attendance.services.attendance_service import (
    start_flexible_attendance_session, eligible_students_for_session,
    scan_attendance,
)
from apps.attendance.utils.qr_tokens import generate_token
from core.models import AuditEvent

from .models import (
    AcademicTerm, Programme, ProgrammeLevel, Specialization, Curriculum,
    CurriculumCourse, StudentAcademicProfile, CurriculumRegistration,
    Course, Department, SchoolYear, Semester, CourseOffering, Enrollment,
)
from .services.curriculum_service import (
    CurriculumError, complete_registration, registration_state,
    publish_curriculum, create_configuration, assign_semester_term,
)


class CurriculumRegistrationTests(TestCase):
    endpoint = "/api/v1/students/me/curriculum-registration/"

    def setUp(self):
        self.client = APIClient()
        self.today = timezone.localdate()
        self.department = Department.objects.create(name="Engineering", code="CURR")
        self.programme = Programme.objects.create(department=self.department, code="ENG", name="Engineering")
        self.level = ProgrammeLevel.objects.create(programme=self.programme, code="YEAR-X", name="Configured level", specialization_required=True)
        self.student = self.user("student")
        self.lecturer = self.user("lecturer", role=User.Role.LECTURER)
        self.admin = self.user("admin", role=User.Role.ADMINISTRATOR)
        self.profile = StudentAcademicProfile.objects.create(student=self.student, programme=self.programme, programme_level=self.level, cohort=2026)
        self.term = AcademicTerm.objects.create(code="FIRST", name="First term")
        self.other_term = AcademicTerm.objects.create(code="SECOND", name="Second term")
        self.year = SchoolYear.objects.create(
            name="Curriculum year", start_date=self.today - timedelta(days=30),
            end_date=self.today + timedelta(days=300),
        )
        self.semester = Semester.objects.create(
            school_year=self.year, name="Current", start_date=self.today - timedelta(days=10),
            end_date=self.today + timedelta(days=100), registration_deadline=self.today + timedelta(days=20),
            is_current=True, academic_term=self.term,
        )
        self.next_semester = Semester.objects.create(
            school_year=self.year, name="Next", start_date=self.today - timedelta(days=1),
            end_date=self.today + timedelta(days=150), academic_term=self.other_term,
        )
        self.specialization = Specialization.objects.create(programme=self.programme, code="SYS", name="Systems")
        self.other_specialization = Specialization.objects.create(programme=self.programme, code="CIV", name="Civil")
        self.curriculum = Curriculum.objects.create(programme=self.programme, version=1, cohort_from=2026, cohort_to=2026)
        self.common = self.requirement("CORE")
        self.specialized = self.requirement("SPEC", specialization=self.specialization, classification="SPECIALIZATION_CORE")
        self.other_specialized = self.requirement("OTHER", specialization=self.other_specialization, classification="SPECIALIZATION_CORE")
        self.elective = self.requirement("ELECT", classification="ELECTIVE", is_required=False)
        self.optional = self.requirement("OPT", is_required=False)
        self.future = self.requirement("FUTURE", term=self.other_term)
        publish_curriculum(actor=self.admin, curriculum_id=self.curriculum.pk)
        self.client.force_authenticate(self.student)

    def user(self, label, **kwargs):
        return User.objects.create_user(
            label + "@curriculum.test", label, label.title(), "Curriculum", "StrongPass!2026",
            department=self.department, level=self.level.code, **kwargs,
        )

    def requirement(self, code, *, specialization=None, classification="PROGRAMME_CORE", is_required=True, term=None):
        course = Course.objects.create(code=code, name=code, department=self.department, level=self.level.code)
        row = CurriculumCourse.objects.create(
            curriculum=self.curriculum, programme_level=self.level, academic_term=term or self.term,
            course=course, specialization=specialization, classification=classification, is_required=is_required,
        )
        offering = CourseOffering.objects.create(
            course=course, semester=self.next_semester if term == self.other_term else self.semester,
            department=self.department, lecturer=self.lecturer,
        )
        return row, offering

    def complete(self, **kwargs):
        return complete_registration(actor=self.student, specialization=self.specialization.pk, **kwargs)

    def test_options_are_programme_scoped_and_level_is_configured(self):
        foreign = Programme.objects.create(department=self.department, code="OTHER", name="Other")
        hidden = Specialization.objects.create(programme=foreign, code="SYS", name="Foreign")
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200)
        data = response.data["data"]
        self.assertEqual(data["level"], "YEAR-X")
        self.assertTrue(data["specialization_required"])
        self.assertNotIn(str(hidden.pk), [row["id"] for row in data["specializations"]])
        self.assertFalse(data["completed"])
        self.assertFalse(Enrollment.objects.exists())
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.curriculum_id)

    def test_completion_enrolls_only_common_and_selected_required_current_offerings(self):
        response = self.client.post(self.endpoint, {"specialization": str(self.specialization.pk)}, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data["data"]["completed"])
        enrollments = Enrollment.objects.filter(student=self.student)
        self.assertEqual(set(enrollments.values_list("course_offering_id", flat=True)), {self.common[1].pk, self.specialized[1].pk})
        self.assertEqual(set(enrollments.values_list("source", flat=True)), {"CURRICULUM"})
        self.assertEqual(set(enrollments.values_list("curriculum_requirement_id", flat=True)), {self.common[0].pk, self.specialized[0].pk})
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.curriculum_id, self.curriculum.pk)
        self.assertEqual(self.profile.specialization_id, self.specialization.pk)
        self.assertEqual(CurriculumRegistration.objects.get().offering_ids, sorted([str(self.common[1].pk), str(self.specialized[1].pk)]))

    def test_retry_is_idempotent_without_reauditing_or_renotifying(self):
        with patch("apps.academic.services.curriculum_service.notify_student_enrolled") as notify:
            with self.captureOnCommitCallbacks(execute=True):
                first = self.complete()
            self.assertEqual(notify.call_count, 2)
            count = AuditEvent.objects.count()
            with self.captureOnCommitCallbacks(execute=True):
                second = complete_registration(actor=self.student)
            self.assertEqual(notify.call_count, 2)
        self.assertEqual(first["registration"], second["registration"])
        self.assertEqual(second["created_enrollments"], [])
        self.assertEqual(Enrollment.objects.count(), 2)
        self.assertEqual(AuditEvent.objects.count(), count)

    def test_no_specialization_programme_completes_without_selection(self):
        self.level.specialization_required = False
        self.level.save()
        result = complete_registration(actor=self.student)
        self.assertTrue(result["completed"])
        self.assertEqual(Enrollment.objects.get().course_offering_id, self.common[1].pk)
        self.assertIsNone(result["specialization"])

    def test_specialization_cannot_be_pinned_before_required_stage(self):
        self.level.specialization_required = False
        self.level.save()
        # Legacy signup text is not the official level or permission to branch.
        User.objects.filter(pk=self.student.pk).update(level="L400")
        response = self.client.post(self.endpoint, {"specialization": str(self.specialization.pk)}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "SPECIALIZATION_NOT_AVAILABLE")
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.specialization_id)
        self.assertIsNone(self.profile.curriculum_id)
        self.assertFalse(Enrollment.objects.exists())
        state = registration_state(actor=self.student)
        self.assertEqual(state["specializations"], [])
        self.assertEqual(state["level"], self.level.code)
        self.assertTrue(complete_registration(actor=self.student, specialization=None)["completed"])

    def test_uncompleted_state_is_readable_after_semester_and_offering_deadlines(self):
        Semester.objects.filter(pk=self.semester.pk).update(registration_deadline=self.today - timedelta(days=1))
        CourseOffering.objects.filter(pk=self.common[1].pk).update(registration_deadline=self.today - timedelta(days=1))
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(response.data["data"]["registration_open"])
        self.assertFalse(response.data["data"]["completed"])
        self.assertFalse(response.data["data"]["required_offerings"][0]["is_available"])
        with self.assertRaises(CurriculumError) as caught:
            self.complete()
        self.assertEqual(caught.exception.code, "REGISTRATION_CLOSED")
        self.assertFalse(Enrollment.objects.exists())

    def test_completed_state_and_replay_return_snapshot_after_closure_and_retirement(self):
        first = self.complete()
        before_audits = AuditEvent.objects.count()
        Semester.objects.filter(pk=self.semester.pk).update(
            registration_deadline=self.today - timedelta(days=1), status="INACTIVE",
        )
        CourseOffering.objects.filter(pk=self.common[1].pk).update(status="INACTIVE")
        Course.objects.filter(pk=self.common[0].course_id).update(name="Renamed after registration", status="INACTIVE")
        self.specialization.is_active = False
        self.specialization.save()
        with patch("apps.academic.services.curriculum_service._required_offerings", side_effect=AssertionError("must not re-resolve")):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                read = self.client.get(self.endpoint)
                replay = self.client.post(self.endpoint, {"specialization": str(self.specialization.pk)}, format="json")
        self.assertEqual(read.status_code, 200, read.data)
        self.assertEqual(replay.status_code, 200, replay.data)
        self.assertEqual(read.data["data"]["required_offerings"], first["required_offerings"])
        self.assertEqual(replay.data["data"]["required_offerings"], first["required_offerings"])
        self.assertEqual(replay.data["data"]["registration"], first["registration"])
        self.assertEqual(replay.data["data"]["created_enrollments"], [])
        self.assertEqual(callbacks, [])
        self.assertEqual(AuditEvent.objects.count(), before_audits)
        self.assertEqual(Enrollment.objects.count(), 2)

    def test_closed_semester_does_not_allow_changed_specialization_on_replay(self):
        self.complete()
        Semester.objects.filter(pk=self.semester.pk).update(registration_deadline=self.today - timedelta(days=1))
        response = self.client.post(self.endpoint, {"specialization": str(self.other_specialization.pk)}, format="json")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["error"]["code"], "SPECIALIZATION_LOCKED")

    def test_registration_get_never_acquires_row_locks(self):
        with patch.object(QuerySet, "select_for_update", side_effect=AssertionError("GET must not lock")):
            self.assertFalse(registration_state(actor=self.student)["completed"])
        self.complete()
        with patch.object(QuerySet, "select_for_update", side_effect=AssertionError("GET must not lock")):
            self.assertTrue(registration_state(actor=self.student)["completed"])

    def test_completion_locks_only_student_profile_and_enrollments(self):
        locked_models = set()
        original = QuerySet.select_for_update
        def track_locks(queryset, *args, **kwargs):
            locked_models.add(queryset.model)
            return original(queryset, *args, **kwargs)
        with patch.object(QuerySet, "select_for_update", track_locks):
            self.complete()
        self.assertEqual(locked_models, {StudentAcademicProfile, Enrollment})

    def test_missing_required_specialization_rejected_without_writes(self):
        response = self.client.post(self.endpoint, {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "SPECIALIZATION_REQUIRED")
        self.assertFalse(Enrollment.objects.exists())

    def test_foreign_inactive_and_unknown_specializations_indistinguishable(self):
        foreign = Programme.objects.create(department=self.department, code="FOR", name="Foreign")
        choice = Specialization.objects.create(programme=foreign, code="FOR", name="Foreign")
        self.other_specialization.is_active = False
        self.other_specialization.save()
        bodies = []
        for pk in (choice.pk, self.other_specialization.pk, uuid4()):
            response = self.client.post(self.endpoint, {"specialization": str(pk)}, format="json")
            self.assertEqual(response.status_code, 400)
            bodies.append(response.data)
        self.assertEqual(bodies[0], bodies[1])
        self.assertEqual(bodies[1], bodies[2])

    def test_specialization_change_and_clear_rejected(self):
        self.complete()
        for pk in (str(self.other_specialization.pk), None):
            response = self.client.post(self.endpoint, {"specialization": pk}, format="json")
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.data["error"]["code"], "SPECIALIZATION_LOCKED")
        self.assertEqual(Enrollment.objects.count(), 2)

    def test_all_server_owned_and_unknown_input_fields_rejected(self):
        for field in ("student", "programme", "department", "level", "cohort", "curriculum", "course", "offering_ids", "role", "completed", "arbitrary"):
            with self.subTest(field=field):
                response = self.client.post(self.endpoint, {"specialization": str(self.specialization.pk), field: str(uuid4())}, format="json")
                self.assertEqual(response.status_code, 400)
        self.assertFalse(Enrollment.objects.exists())

    def test_anonymous_lecturer_admin_and_staff_flag_cannot_complete_for_student(self):
        self.client.force_authenticate(None)
        self.assertIn(self.client.post(self.endpoint, {}, format="json").status_code, (401, 403))
        for actor in (self.lecturer, self.admin):
            self.client.force_authenticate(actor)
            self.assertEqual(self.client.post(self.endpoint, {}, format="json").status_code, 403)
        self.student.is_staff = True
        self.student.save()
        self.client.force_authenticate(self.student)
        self.assertEqual(self.client.get("/api/v1/admin/curriculum/profiles/").status_code, 403)

    def test_missing_profile_explicit(self):
        self.profile.delete()
        response = self.client.get(self.endpoint)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["error"]["code"], "INCOMPLETE_ACADEMIC_PROFILE")

    def test_client_chosen_legacy_level_cannot_change_official_curriculum_level(self):
        stale = self.student
        User.objects.filter(pk=stale.pk).update(level="UNCONFIGURED")
        result = complete_registration(actor=stale, specialization=self.specialization.pk)
        self.assertEqual(result["level"], self.level.code)
        self.assertTrue(result["completed"])

    def test_student_department_must_match_admin_owned_programme(self):
        User.objects.filter(pk=self.student.pk).update(department=None)
        with self.assertRaises(CurriculumError):
            self.complete()
        self.assertFalse(Enrollment.objects.exists())

    def test_missing_or_unpublished_curriculum_explicit(self):
        Curriculum.objects.filter(pk=self.curriculum.pk).update(is_published=False)
        with self.assertRaises(CurriculumError):
            self.complete()
        self.assertFalse(Enrollment.objects.exists())

    def test_missing_term_and_no_current_semester_explicit(self):
        Semester.objects.filter(pk=self.semester.pk).update(academic_term=None)
        with self.assertRaises(CurriculumError):
            self.complete()
        Semester.objects.filter(pk=self.semester.pk).update(is_current=False)
        with self.assertRaises(CurriculumError) as caught:
            self.complete()
        self.assertEqual(caught.exception.code, "NO_ACTIVE_SEMESTER")

    def test_missing_or_inactive_required_offering_rolls_back_everything(self):
        self.specialized[1].status = "INACTIVE"
        self.specialized[1].save()
        audit_count = AuditEvent.objects.count()
        with self.assertRaises(CurriculumError) as caught:
            self.complete()
        self.assertEqual(caught.exception.code, "REQUIRED_OFFERING_UNAVAILABLE")
        self.assertFalse(Enrollment.objects.exists())
        self.assertFalse(CurriculumRegistration.objects.exists())
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.curriculum_id)
        self.assertEqual(AuditEvent.objects.count(), audit_count)

    def test_other_semester_offering_cannot_substitute_required_current_offering(self):
        self.specialized[1].semester = self.next_semester
        self.specialized[1].save()
        with self.assertRaises(CurriculumError) as caught:
            self.complete()
        self.assertEqual(caught.exception.code, "REQUIRED_OFFERING_UNAVAILABLE")

    def test_semester_and_offering_deadlines_enforced(self):
        self.semester.registration_deadline = self.today - timedelta(days=1)
        self.semester.save()
        with self.assertRaises(CurriculumError) as caught:
            self.complete()
        self.assertEqual(caught.exception.code, "REGISTRATION_CLOSED")
        self.semester.registration_deadline = self.today
        self.semester.save()
        self.specialized[1].registration_deadline = self.today - timedelta(days=1)
        self.specialized[1].save()
        with self.assertRaises(CurriculumError) as caught:
            self.complete()
        self.assertEqual(caught.exception.code, "REGISTRATION_CLOSED")

    def test_current_active_semester_allows_registration_before_teaching_starts(self):
        self.semester.start_date = self.today + timedelta(days=5)
        self.semester.save()
        self.assertTrue(self.complete()["completed"])

    def test_existing_active_manual_and_unrelated_enrollments_are_unchanged(self):
        manual = Enrollment.objects.create(
            student=self.student, course=self.common[0].course, course_offering=self.common[1],
            enrolled_by=self.admin, reason="Manual admission",
        )
        unrelated = Enrollment.objects.create(student=self.student, course=self.elective[0].course, course_offering=self.elective[1])
        before = Enrollment.objects.filter(pk__in=[manual.pk, unrelated.pk]).values().order_by("pk")
        snapshot = list(before)
        self.complete()
        self.assertEqual(list(before), snapshot)
        self.assertEqual(Enrollment.objects.count(), 3)

    def test_inactive_required_enrollment_is_conflict_and_drop_history_is_preserved(self):
        dropped = Enrollment.objects.create(
            student=self.student, course=self.specialized[0].course, course_offering=self.specialized[1],
            is_active=False, status="dropped", dropped_by=self.admin, dropped_at=timezone.now(),
            reason="Institutional hold", source="CURRICULUM", curriculum_requirement=self.specialized[0],
        )
        before = Enrollment.objects.filter(pk=dropped.pk).values().get()
        with self.assertRaises(CurriculumError) as caught:
            self.complete()
        self.assertEqual(caught.exception.code, "ENROLLMENT_CONFLICT")
        self.assertEqual(Enrollment.objects.filter(pk=dropped.pk).values().get(), before)
        self.assertEqual(Enrollment.objects.count(), 1)
        self.assertFalse(CurriculumRegistration.objects.exists())

    def test_legacy_course_enrollment_does_not_replace_exact_offering_enrollment(self):
        legacy = Enrollment.objects.create(student=self.student, course=self.common[0].course)
        self.complete()
        legacy.refresh_from_db()
        self.assertIsNone(legacy.course_offering_id)
        self.assertEqual(legacy.source, "LEGACY")
        self.assertEqual(Enrollment.objects.count(), 3)

    def test_audit_failure_rolls_back_enrollments_profile_registration_and_callbacks(self):
        audit_count = AuditEvent.objects.count()
        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with patch("apps.academic.services.curriculum_service.write_audit_entry", side_effect=RuntimeError("audit unavailable")):
                with self.assertRaises(RuntimeError):
                    self.complete()
        self.assertEqual(callbacks, [])
        self.assertFalse(Enrollment.objects.exists())
        self.assertFalse(CurriculumRegistration.objects.exists())
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.curriculum_id)
        self.assertEqual(AuditEvent.objects.count(), audit_count)

    def test_late_audit_failure_rolls_back_already_written_profile(self):
        from apps.academic.services import curriculum_service
        real_audit = curriculum_service.write_audit_entry
        def fail_final(**kwargs):
            if kwargs["action"] == "curriculum_registration_completed":
                raise RuntimeError("audit unavailable")
            return real_audit(**kwargs)
        before = AuditEvent.objects.count()
        with patch("apps.academic.services.curriculum_service.write_audit_entry", side_effect=fail_final):
            with self.assertRaises(RuntimeError):
                self.complete()
        self.profile.refresh_from_db()
        self.assertIsNone(self.profile.curriculum_id)
        self.assertFalse(Enrollment.objects.exists())
        self.assertFalse(CurriculumRegistration.objects.exists())
        self.assertEqual(AuditEvent.objects.count(), before)

    def test_notification_failure_after_commit_does_not_revert_academic_result(self):
        with patch("apps.academic.services.curriculum_service.notify_student_enrolled", side_effect=RuntimeError("delivery failed")):
            with self.assertLogs("django.test", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    result = self.complete()
        self.assertTrue(result["completed"])
        self.assertEqual(Enrollment.objects.count(), 2)

    def test_next_term_uses_pinned_version_and_preserves_previous_registration(self):
        first = self.complete()
        self.next_semester.is_current = True
        self.next_semester.save()
        second = complete_registration(actor=self.student)
        self.assertNotEqual(first["registration"], second["registration"])
        self.assertEqual(second["curriculum"]["id"], first["curriculum"]["id"])
        self.assertEqual([item["offering"] for item in second["required_offerings"]], [str(self.future[1].pk)])
        self.assertEqual(CurriculumRegistration.objects.count(), 2)
        self.assertEqual(Enrollment.objects.count(), 3)

    def test_changed_current_level_cannot_rewrite_registered_semester(self):
        first = self.complete()
        other_level = ProgrammeLevel.objects.create(programme=self.programme, code="YEAR-Y", name="Next level")
        StudentAcademicProfile.objects.filter(pk=self.profile.pk).update(programme_level=other_level)
        replay = complete_registration(actor=self.student)
        self.assertEqual(replay["level"], first["level"])
        self.assertEqual(CurriculumRegistration.objects.get().programme_level_id, self.level.pk)

    def test_curriculum_enrollment_feeds_real_attendance_roster_and_scan(self):
        session = start_flexible_attendance_session(actor=self.lecturer, offering_id=self.common[1].pk)
        self.assertEqual(eligible_students_for_session(session=session), [])
        self.complete()
        self.assertEqual([row.pk for row in eligible_students_for_session(session=session)], [self.student.pk])
        # Projected mode: the room's single code credits the scanner the
        # curriculum just enrolled, and a projected scan has no scan point.
        token = generate_token(session_id=session.pk)
        record = scan_attendance(authenticated_student=self.student, token=token)
        self.assertEqual(record.student_id, self.student.pk)
        self.assertIsNone(record.checkpoint_id)
        other_session = start_flexible_attendance_session(actor=self.lecturer, offering_id=self.other_specialized[1].pk)
        self.assertEqual(eligible_students_for_session(session=other_session), [])

    def test_configuration_api_requires_admin_before_fk_resolution(self):
        payload = {"student": str(uuid4()), "programme": str(uuid4()), "cohort": 2026}
        for actor in (self.student, self.lecturer):
            self.client.force_authenticate(actor)
            response = self.client.post("/api/v1/admin/curriculum/profiles/", payload, format="json")
            self.assertEqual(response.status_code, 403)
        with self.assertRaises(CurriculumError) as caught:
            create_configuration(actor=self.student, resource="terms", data={"code": "X", "name": "X"})
        self.assertEqual(caught.exception.status, 403)

    def test_admin_configuration_creates_profile_and_rejects_pin_injection(self):
        other = self.user("newstudent")
        self.client.force_authenticate(self.admin)
        payload = {"student": str(other.pk), "programme": str(self.programme.pk), "programme_level": str(self.level.pk), "cohort": 2026}
        response = self.client.post("/api/v1/admin/curriculum/profiles/", {**payload, "curriculum": str(self.curriculum.pk)}, format="json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/v1/admin/curriculum/profiles/", payload, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertTrue(StudentAcademicProfile.objects.filter(student=other).exists())
        self.assertTrue(AuditEvent.objects.filter(action="curriculum_configuration_created", resource_id=str(other.pk)).exists())

    def test_admin_profile_creation_requires_explicit_level_within_programme(self):
        other = self.user("profile-level-student")
        self.client.force_authenticate(self.admin)
        payload = {"student": str(other.pk), "programme": str(self.programme.pk), "cohort": 2026}
        response = self.client.post("/api/v1/admin/curriculum/profiles/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        foreign_programme = Programme.objects.create(department=self.department, code="LEVEL-FOR", name="Foreign")
        foreign_level = ProgrammeLevel.objects.create(programme=foreign_programme, code=self.level.code, name="Foreign level")
        response = self.client.post("/api/v1/admin/curriculum/profiles/", {**payload, "programme_level": str(foreign_level.pk)}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StudentAcademicProfile.objects.filter(student=other).exists())

    def test_admin_can_configure_new_programme_without_hardcoded_levels(self):
        self.client.force_authenticate(self.admin)
        response = self.client.post("/api/v1/admin/curriculum/programmes/", {
            "department": str(self.department.pk), "code": "NEW", "name": "New programme",
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        response = self.client.post("/api/v1/admin/curriculum/levels/", {
            "programme": response.data["data"]["id"], "code": "ADV", "name": "Advanced",
            "specialization_required": False,
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)

    def test_published_curriculum_rejects_requirement_additions(self):
        with self.assertRaises(CurriculumError) as caught:
            create_configuration(actor=self.admin, resource="requirements", data={
                "curriculum": self.curriculum, "programme_level": self.level,
                "academic_term": self.term, "course": self.future[0].course,
                "classification": "PROGRAMME_CORE", "is_required": True,
            })
        self.assertEqual(caught.exception.code, "CURRICULUM_FROZEN")

    def test_required_elective_rejected_by_service_and_database(self):
        draft = Curriculum.objects.create(programme=self.programme, version=2, cohort_from=2027, cohort_to=2027)
        data = {
            "curriculum": draft, "programme_level": self.level, "academic_term": self.term,
            "course": self.elective[0].course, "classification": "ELECTIVE", "is_required": True,
        }
        with self.assertRaises(CurriculumError):
            create_configuration(actor=self.admin, resource="requirements", data=data)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CurriculumCourse.objects.create(**data)

    def test_cross_programme_requirement_rejected(self):
        draft = Curriculum.objects.create(programme=self.programme, version=2, cohort_from=2027, cohort_to=2027)
        other = Programme.objects.create(department=self.department, code="FOREIGN", name="Foreign")
        level = ProgrammeLevel.objects.create(programme=other, code=self.level.code, name="Other")
        with self.assertRaises(CurriculumError):
            create_configuration(actor=self.admin, resource="requirements", data={
                "curriculum": draft, "programme_level": level, "academic_term": self.term,
                "course": self.common[0].course, "classification": "PROGRAMME_CORE",
            })

    def test_overlapping_published_cohort_versions_rejected(self):
        draft = Curriculum.objects.create(programme=self.programme, version=2, cohort_from=2026, cohort_to=2027)
        with self.assertRaises(CurriculumError) as caught:
            publish_curriculum(actor=self.admin, curriculum_id=draft.pk)
        self.assertEqual(caught.exception.code, "COHORT_CONFLICT")

    def test_registered_semester_term_mapping_cannot_change(self):
        self.complete()
        with self.assertRaises(CurriculumError) as caught:
            assign_semester_term(actor=self.admin, semester_id=self.semester.pk, academic_term=self.other_term)
        self.assertEqual(caught.exception.code, "TERM_LOCKED")

    def test_admin_term_mapping_api_and_empty_publish_body(self):
        self.client.force_authenticate(self.admin)
        response = self.client.put("/api/v1/admin/semesters/" + str(self.next_semester.pk) + "/curriculum-term/", {"academic_term": str(self.term.pk)}, format="json")
        self.assertEqual(response.status_code, 200)
        response = self.client.post("/api/v1/admin/curricula/" + str(self.curriculum.pk) + "/publish/", {"is_published": True}, format="json")
        self.assertEqual(response.status_code, 400)
