import shutil
import tempfile
import uuid
from datetime import date
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import User
from apps.academic.models import (
    Course,
    CourseOffering,
    Department,
    Enrollment,
    Faculty,
    SchoolYear,
    Semester,
)
from core.models import AuditEvent

from .models import LearningMaterial, UploadedFile
from .services.file_service import create_material


class PrivateCourseFileApiTests(APITestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.media_root = tempfile.mkdtemp(prefix="fet-files-tests-")
        cls.media_override = override_settings(MEDIA_ROOT=cls.media_root)
        cls.media_override.enable()

    @classmethod
    def tearDownClass(cls):
        cls.media_override.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    def setUp(self):
        self.faculty = Faculty.objects.create(name="Engineering")
        self.department = Department.objects.create(
            name="Computing", code="CMP", faculty=self.faculty
        )
        self.other_department = Department.objects.create(
            name="Business", code="BUS", faculty=self.faculty
        )
        self.year = SchoolYear.objects.create(
            name="2026/2027", start_date=date(2026, 9, 1), end_date=date(2027, 7, 31)
        )
        self.semester = Semester.objects.create(
            school_year=self.year,
            name="Semester 1",
            start_date=date(2026, 9, 1),
            end_date=date(2027, 1, 31),
            is_current=True,
        )
        self.lecturer = self._user("lecturer", User.Role.LECTURER)
        self.foreign_lecturer = self._user("foreign", User.Role.LECTURER)
        self.student = self._user("student", User.Role.STUDENT)
        self.outsider = self._user("outsider", User.Role.STUDENT)
        self.admin = self._user("admin", User.Role.ADMINISTRATOR, is_staff=True)
        self.course = Course.objects.create(
            code="CSC401", name="Secure Systems", department=self.department, level="400"
        )
        self.other_course = Course.objects.create(
            code="BUS401", name="Audit", department=self.other_department, level="400"
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
            department=self.other_department,
            lecturer=self.foreign_lecturer,
        )
        Enrollment.objects.create(
            student=self.student,
            course=self.course,
            course_offering=self.offering,
            status="active",
            is_active=True,
        )

    def _user(self, prefix, role, **extra):
        return User.objects.create_user(
            email=f"{prefix}@example.test",
            username=prefix,
            first_name=prefix.title(),
            last_name="User",
            password="Strong-Pass-2026!",
            role=role,
            is_email_verified=True,
            **extra,
        )

    def _pdf(self, name="notes.pdf", body=b"%PDF-1.7\ncourse notes"):
        return SimpleUploadedFile(name, body, content_type="application/octet-stream")

    def _upload(self, actor=None, offering=None, upload=None, **extra):
        self.client.force_authenticate(actor or self.lecturer)
        data = {
            "course_offering": str((offering or self.offering).id),
            "file": upload or self._pdf(),
            **extra,
        }
        return self.client.post("/api/v1/files/", data, format="multipart")

    def _uploaded_record(self):
        response = self._upload()
        self.assertEqual(response.status_code, 201, response.data)
        return UploadedFile.objects.get(pk=response.data["data"]["id"]), response

    def _material(self):
        record, _ = self._uploaded_record()
        self.client.force_authenticate(self.lecturer)
        response = self.client.post(
            f"/api/v1/course-offerings/{self.offering.id}/materials/",
            {"title": "Week 1", "description": "Read before class", "file": str(record.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        return LearningMaterial.objects.get(pk=response.data["data"]["id"]), record

    def test_upload_is_scoped_and_uses_detected_type_without_storage_location(self):
        record, response = self._uploaded_record()
        self.assertEqual(record.course_offering, self.offering)
        self.assertEqual(record.mime_type, "application/pdf")
        self.assertEqual(response.data["data"]["mime_type"], "application/pdf")
        self.assertNotIn("file", response.data["data"])
        self.assertNotIn("url", response.data["data"])
        self.assertTrue(AuditEvent.objects.filter(action="file_uploaded").exists())

    def test_foreign_lecturer_and_missing_offering_have_identical_404(self):
        foreign = self._upload(actor=self.foreign_lecturer)
        missing = self._upload(
            actor=self.foreign_lecturer,
            offering=type("OfferingId", (), {"id": uuid.uuid4()})(),
        )
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(foreign.data, missing.data)

    def test_student_cannot_upload_even_when_enrolled(self):
        response = self._upload(actor=self.student)
        self.assertEqual(response.status_code, 403)

    def test_lecturer_approval_is_enforced_for_file_management(self):
        pending = self._user(
            "pending-files",
            User.Role.LECTURER,
            lecturer_approval_status=User.LecturerApproval.PENDING,
        )
        self.offering.lecturer = pending
        self.offering.save(update_fields=["lecturer", "updated_at"])

        denied_upload = self._upload(actor=pending)
        self.assertEqual(denied_upload.status_code, 403)
        self.assertEqual(UploadedFile.objects.count(), 0)

        pending.lecturer_approval_status = User.LecturerApproval.APPROVED
        pending.save(update_fields=["lecturer_approval_status", "updated_at"])
        approved_upload = self._upload(actor=pending)
        self.assertEqual(approved_upload.status_code, 201, approved_upload.data)

        pending.lecturer_approval_status = User.LecturerApproval.REJECTED
        pending.save(update_fields=["lecturer_approval_status", "updated_at"])
        record = UploadedFile.objects.get(pk=approved_upload.data["data"]["id"])
        denied_create = self.client.post(
            f"/api/v1/course-offerings/{self.offering.id}/materials/",
            {"title": "Denied", "file": str(record.id)},
            format="json",
        )
        denied_download = self.client.get(f"/api/v1/files/{record.id}/")
        self.assertEqual(denied_create.status_code, 403)
        self.assertEqual(denied_download.status_code, 404)
        self.assertEqual(LearningMaterial.objects.count(), 0)

    def test_file_access_matrix_preserves_legacy_and_resource_scope(self):
        # Legacy lecturers have NULL approval status and retain compatibility.
        self.assertIsNone(self.lecturer.lecturer_approval_status)
        legacy = self._upload(actor=self.lecturer, offering=self.offering)
        self.assertEqual(legacy.status_code, 201, legacy.data)

        # Approval establishes lecturer identity only; it does not grant access
        # to another lecturer's offering.
        self.foreign_lecturer.lecturer_approval_status = User.LecturerApproval.APPROVED
        self.foreign_lecturer.save(
            update_fields=["lecturer_approval_status", "updated_at"]
        )
        unrelated = self._upload(
            actor=self.foreign_lecturer,
            offering=self.offering,
            upload=self._pdf(name="unrelated.pdf"),
        )
        own = self._upload(
            actor=self.foreign_lecturer,
            offering=self.other_offering,
            upload=self._pdf(name="own-offering.pdf"),
        )
        self.assertEqual(unrelated.status_code, 404)
        self.assertEqual(own.status_code, 201, own.data)

        # Administrators retain the platform-wide management authority defined
        # by the central policy.
        admin = self._upload(
            actor=self.admin,
            offering=self.other_offering,
            upload=self._pdf(name="admin.pdf"),
        )
        self.assertEqual(admin.status_code, 201, admin.data)

    def test_mime_spoof_and_dangerous_double_extension_are_rejected(self):
        spoof = self._upload(upload=SimpleUploadedFile("attack.pdf", b"MZ executable"))
        self.assertEqual(spoof.status_code, 400)
        double = self._upload(upload=self._pdf(name="attack.exe.pdf"))
        self.assertEqual(double.status_code, 400)
        self.assertEqual(UploadedFile.objects.count(), 0)

    @override_settings(MAX_FILE_SIZE_BYTES=8)
    def test_size_limit_is_enforced_before_storage(self):
        response = self._upload(upload=self._pdf(body=b"%PDF-1.7 too large"))
        self.assertEqual(response.status_code, 400)
        self.assertEqual(UploadedFile.objects.count(), 0)

    def test_unknown_upload_and_material_fields_are_rejected(self):
        upload = self._upload(role="ADMINISTRATOR")
        self.assertEqual(upload.status_code, 400)
        record, _ = self._uploaded_record()
        self.client.force_authenticate(self.lecturer)
        material = self.client.post(
            f"/api/v1/course-offerings/{self.offering.id}/materials/",
            {
                "title": "Notes",
                "file": str(record.id),
                "course_offering": str(self.other_offering.id),
            },
            format="json",
        )
        self.assertEqual(material.status_code, 400)
        self.assertEqual(LearningMaterial.objects.count(), 0)

    def test_file_cannot_be_attached_to_another_offering(self):
        record, _ = self._uploaded_record()
        self.client.force_authenticate(self.admin)
        response = self.client.post(
            f"/api/v1/course-offerings/{self.other_offering.id}/materials/",
            {"title": "Cross scope", "file": str(record.id)},
            format="json",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(LearningMaterial.objects.count(), 0)

    def test_enrolled_student_can_list_and_download_private_material(self):
        material, record = self._material()
        self.client.force_authenticate(self.student)
        listing = self.client.get(
            f"/api/v1/course-offerings/{self.offering.id}/materials/"
        )
        self.assertEqual(listing.status_code, 200)
        self.assertEqual(listing.data["data"][0]["id"], str(material.id))
        download = self.client.get(f"/api/v1/files/{record.id}/")
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download["Cache-Control"], "private, no-store")
        self.assertEqual(download["X-Content-Type-Options"], "nosniff")
        self.assertEqual(b"".join(download.streaming_content), b"%PDF-1.7\ncourse notes")

    def test_unenrolled_and_missing_file_have_identical_404(self):
        _, record = self._material()
        self.client.force_authenticate(self.outsider)
        foreign = self.client.get(f"/api/v1/files/{record.id}/")
        missing = self.client.get(f"/api/v1/files/{uuid.uuid4()}/")
        self.assertEqual(foreign.status_code, 404)
        self.assertEqual(foreign.data, missing.data)

    def test_update_and_delete_archive_with_audit_and_block_download(self):
        material, record = self._material()
        self.client.force_authenticate(self.lecturer)
        update = self.client.patch(
            f"/api/v1/materials/{material.id}/",
            {"title": "Revised", "unexpected": "ignored?"},
            format="json",
        )
        self.assertEqual(update.status_code, 400)
        update = self.client.patch(
            f"/api/v1/materials/{material.id}/",
            {"title": "Revised"},
            format="json",
        )
        self.assertEqual(update.status_code, 200)
        delete = self.client.delete(f"/api/v1/materials/{material.id}/")
        self.assertEqual(delete.status_code, 200)
        material.refresh_from_db()
        record.refresh_from_db()
        self.assertEqual(material.status, LearningMaterial.Status.ARCHIVED)
        self.assertEqual(record.status, UploadedFile.Status.ARCHIVED)
        self.assertTrue(
            AuditEvent.objects.filter(action="learning_material_updated").exists()
        )
        self.assertTrue(
            AuditEvent.objects.filter(action="learning_material_archived").exists()
        )
        self.assertEqual(self.client.get(f"/api/v1/files/{record.id}/").status_code, 404)


    def test_same_file_cannot_back_multiple_active_materials(self):
        record, _ = self._uploaded_record()
        self.client.force_authenticate(self.lecturer)
        url = f"/api/v1/course-offerings/{self.offering.id}/materials/"
        first = self.client.post(url, {"title": "First", "file": str(record.id)}, format="json")
        second = self.client.post(url, {"title": "Second", "file": str(record.id)}, format="json")
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(LearningMaterial.objects.filter(file=record).count(), 1)

    def test_material_creation_rolls_back_when_audit_fails(self):
        record, _ = self._uploaded_record()

        with patch(
            "apps.files.services.file_service.write_audit_entry",
            side_effect=RuntimeError("audit unavailable"),
        ):
            with self.assertRaises(RuntimeError):
                create_material(
                    actor=self.lecturer,
                    offering_id=self.offering.pk,
                    title="Must roll back",
                    file=record.pk,
                )

        self.assertFalse(
            LearningMaterial.objects.filter(title="Must roll back").exists()
        )
