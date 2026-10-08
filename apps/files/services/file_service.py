"""Secure course-file and learning-material business rules."""

import codecs
import hashlib
import zipfile
from pathlib import PurePath

from django.conf import settings
from django.db import transaction

from apps.academic.models import CourseOffering, Enrollment
from core.academic_access import is_admin_user, is_authorized_academic_user, normalize_role
from core.audit import write_audit_entry

from ..models import LearningMaterial, UploadedFile


class FileServiceError(ValueError):
    pass


class ResourceNotFoundError(FileServiceError):
    pass


class FileValidationError(FileServiceError):
    pass


class FileConflictError(FileServiceError):
    pass


ALLOWED_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".txt": "text/plain",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}
DANGEROUS_SUFFIXES = {
    ".exe", ".dll", ".com", ".bat", ".cmd", ".ps1", ".sh", ".js", ".html",
    ".htm", ".svg", ".php", ".py", ".jar", ".msi", ".scr",
}


def _is_admin(user):
    return is_admin_user(user)


def _is_manager(user, offering):
    return _is_admin(user) or (
        is_authorized_academic_user(user)
        and normalize_role(getattr(user, "role", None)) == "lecturer"
        and offering.lecturer_id == getattr(user, "id", None)
    )


def _is_enrolled(user, offering):
    return (
        normalize_role(getattr(user, "role", None)) == "student"
        and Enrollment.objects.filter(
            student=user,
            course_offering=offering,
            is_active=True,
            status__iexact="active",
        ).exists()
    )


def _can_read(user, offering):
    return _is_manager(user, offering) or _is_enrolled(user, offering)


def _manageable_offering(user, offering_id):
    queryset = CourseOffering.objects.select_related("course", "lecturer")
    if _is_admin(user):
        return queryset.filter(pk=offering_id).first()
    if (
        is_authorized_academic_user(user)
        and normalize_role(getattr(user, "role", None)) == "lecturer"
    ):
        return queryset.filter(pk=offering_id, lecturer=user).first()
    return None


def _readable_offering(user, offering_id):
    queryset = CourseOffering.objects.select_related("course", "lecturer")
    if _is_admin(user):
        return queryset.filter(pk=offering_id).first()
    if (
        is_authorized_academic_user(user)
        and normalize_role(getattr(user, "role", None)) == "lecturer"
    ):
        return queryset.filter(pk=offering_id, lecturer=user).first()
    if normalize_role(getattr(user, "role", None)) == "student":
        return queryset.filter(
            pk=offering_id,
            enrollments__student=user,
            enrollments__is_active=True,
            enrollments__status__iexact="active",
        ).distinct().first()
    return None


def _safe_name(raw_name):
    name = str(raw_name or "").strip()
    if not name or len(name) > 255:
        raise FileValidationError("File name is required and must be at most 255 characters.")
    normalized = name.replace("\\", "/")
    if "/" in normalized or PurePath(normalized).name != normalized:
        raise FileValidationError("File name must not contain a path.")
    if any(ord(char) < 32 or ord(char) == 127 for char in normalized):
        raise FileValidationError("File name contains invalid control characters.")
    suffixes = [suffix.lower() for suffix in PurePath(normalized).suffixes]
    if not suffixes or suffixes[-1] not in ALLOWED_BY_EXTENSION:
        raise FileValidationError("File type is not allowed.")
    if any(suffix in DANGEROUS_SUFFIXES for suffix in suffixes[:-1]):
        raise FileValidationError("File name contains a dangerous executable extension.")
    return normalized, suffixes[-1]


def _read_header(upload, length=65536):
    upload.seek(0)
    header = upload.read(length)
    upload.seek(0)
    return header


def _validate_docx(upload):
    upload.seek(0)
    try:
        with zipfile.ZipFile(upload) as archive:
            entries = archive.infolist()
            names = {entry.filename for entry in entries}
            if len(entries) > 2000 or sum(entry.file_size for entry in entries) > 100 * 1024 * 1024:
                raise FileValidationError("Office document expands beyond the safe limit.")
            if "[Content_Types].xml" not in names or not any(
                name.startswith("word/") for name in names
            ):
                raise FileValidationError("The file is not a valid Word document.")
    except (zipfile.BadZipFile, OSError) as exc:
        raise FileValidationError("The file is not a valid Word document.") from exc
    finally:
        upload.seek(0)


def _detected_mime(upload, extension):
    header = _read_header(upload)
    if extension == ".pdf" and header.startswith(b"%PDF-"):
        return ALLOWED_BY_EXTENSION[extension]
    if extension == ".png" and header.startswith(b"\x89PNG\r\n\x1a\n"):
        return ALLOWED_BY_EXTENSION[extension]
    if extension in {".jpg", ".jpeg"} and header.startswith(b"\xff\xd8\xff"):
        return ALLOWED_BY_EXTENSION[extension]
    if extension == ".gif" and header.startswith((b"GIF87a", b"GIF89a")):
        return ALLOWED_BY_EXTENSION[extension]
    if extension == ".webp" and header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return ALLOWED_BY_EXTENSION[extension]
    if extension == ".doc" and header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return ALLOWED_BY_EXTENSION[extension]
    if extension == ".docx":
        _validate_docx(upload)
        return ALLOWED_BY_EXTENSION[extension]
    if extension == ".mp4" and len(header) >= 12 and header[4:8] == b"ftyp":
        return ALLOWED_BY_EXTENSION[extension]
    if extension == ".webm" and header.startswith(b"\x1aE\xdf\xa3"):
        return ALLOWED_BY_EXTENSION[extension]
    if extension == ".txt":
        return ALLOWED_BY_EXTENSION[extension]
    raise FileValidationError("File contents do not match the allowed file extension.")


def _hash_and_measure(upload, mime_type):
    digest = hashlib.sha256()
    total = 0
    text_decoder = codecs.getincrementaldecoder("utf-8")() if mime_type == "text/plain" else None
    upload.seek(0)
    for chunk in upload.chunks():
        total += len(chunk)
        if total > settings.MAX_FILE_SIZE_BYTES:
            raise FileValidationError(
                f"File exceeds the maximum of {settings.MAX_FILE_SIZE_BYTES} bytes."
            )
        digest.update(chunk)
        if text_decoder is not None:
            if b"\x00" in chunk:
                raise FileValidationError("Text files must not contain binary data.")
            try:
                decoded = text_decoder.decode(chunk)
            except UnicodeDecodeError as exc:
                raise FileValidationError("Text files must use UTF-8 encoding.") from exc
            if any(ord(char) < 32 and char not in "\t\r\n" for char in decoded):
                raise FileValidationError("Text files contain invalid control characters.")
    if text_decoder is not None:
        try:
            text_decoder.decode(b"", final=True)
        except UnicodeDecodeError as exc:
            raise FileValidationError("Text files must use UTF-8 encoding.") from exc
    upload.seek(0)
    if total == 0:
        raise FileValidationError("Empty files are not allowed.")
    return total, digest.hexdigest()


def create_uploaded_file(*, actor, offering_id, upload):
    offering = _manageable_offering(actor, offering_id)
    if offering is None:
        raise ResourceNotFoundError("Course offering not found.")
    original_name, extension = _safe_name(upload.name)
    if getattr(upload, "size", 0) > settings.MAX_FILE_SIZE_BYTES:
        raise FileValidationError(
            f"File exceeds the maximum of {settings.MAX_FILE_SIZE_BYTES} bytes."
        )
    mime_type = _detected_mime(upload, extension)
    size_bytes, sha256 = _hash_and_measure(upload, mime_type)
    record = UploadedFile(
        course_offering=offering,
        uploaded_by=actor,
        original_name=original_name,
        mime_type=mime_type,
        size_bytes=size_bytes,
        sha256=sha256,
    )
    stored_name = None
    try:
        with transaction.atomic():
            record.file.save(original_name, upload, save=False)
            stored_name = record.file.name
            record.save()
            write_audit_entry(
                action="file_uploaded",
                resource_type="uploaded_file",
                resource_id=record.id,
                actor_id=actor.id,
                details={
                    "course_offering_id": offering.id,
                    "original_name": original_name,
                    "mime_type": mime_type,
                    "size_bytes": size_bytes,
                    "sha256": sha256,
                },
            )
    except Exception:
        if stored_name:
            record.file.storage.delete(stored_name)
        raise
    return record


def list_materials(*, actor, offering_id):
    offering = _readable_offering(actor, offering_id)
    if offering is None:
        raise ResourceNotFoundError("Course offering not found.")
    return LearningMaterial.objects.filter(
        course_offering=offering,
        status=LearningMaterial.Status.ACTIVE,
        file__status=UploadedFile.Status.ACTIVE,
    ).select_related("file")


def create_material(*, actor, offering_id, title, file, description=""):
    offering = _manageable_offering(actor, offering_id)
    if offering is None:
        raise ResourceNotFoundError("Course offering not found.")
    with transaction.atomic():
        # Serialize competing attachments for the same file. The database
        # unique constraint is the final backstop; this lock keeps the losing
        # request on the documented 409 path instead of an IntegrityError/500.
        uploaded_file = UploadedFile.objects.select_for_update().filter(
            pk=file,
            course_offering=offering,
            status=UploadedFile.Status.ACTIVE,
        ).first()
        if uploaded_file is None:
            raise ResourceNotFoundError("File not found.")
        if LearningMaterial.objects.filter(
            file=uploaded_file, status=LearningMaterial.Status.ACTIVE
        ).exists():
            raise FileConflictError("File is already attached to an active material.")
        material = LearningMaterial.objects.create(
            course_offering=offering,
            uploaded_by=actor,
            title=title,
            description=description,
            file=uploaded_file,
        )
        write_audit_entry(
            action="learning_material_created",
            resource_type="learning_material",
            resource_id=material.id,
            actor_id=actor.id,
            details={"course_offering_id": offering.id, "file_id": uploaded_file.id},
        )
    return material


def get_material(*, actor, material_id, require_manage=False):
    material = LearningMaterial.objects.select_related("course_offering", "file").filter(
        pk=material_id,
        status=LearningMaterial.Status.ACTIVE,
        file__status=UploadedFile.Status.ACTIVE,
    ).first()
    if material is None:
        raise ResourceNotFoundError("Material not found.")
    allowed = _is_manager(actor, material.course_offering) if require_manage else _can_read(
        actor, material.course_offering
    )
    if not allowed:
        raise ResourceNotFoundError("Material not found.")
    return material


def update_material(*, actor, material_id, changes):
    material = get_material(actor=actor, material_id=material_id, require_manage=True)
    old_value = {"title": material.title, "description": material.description}
    for field in ("title", "description"):
        if field in changes:
            setattr(material, field, changes[field])
    with transaction.atomic():
        material.save(update_fields=[*changes.keys(), "updated_at"])
        write_audit_entry(
            action="learning_material_updated",
            resource_type="learning_material",
            resource_id=material.id,
            actor_id=actor.id,
            old_value=old_value,
            new_value={"title": material.title, "description": material.description},
        )
    return material


def archive_material(*, actor, material_id):
    material = get_material(actor=actor, material_id=material_id, require_manage=True)
    with transaction.atomic():
        material.status = LearningMaterial.Status.ARCHIVED
        material.save(update_fields=["status", "updated_at"])
        if not LearningMaterial.objects.filter(
            file=material.file, status=LearningMaterial.Status.ACTIVE
        ).exists():
            material.file.status = UploadedFile.Status.ARCHIVED
            material.file.save(update_fields=["status", "updated_at"])
        write_audit_entry(
            action="learning_material_archived",
            resource_type="learning_material",
            resource_id=material.id,
            actor_id=actor.id,
            details={"course_offering_id": material.course_offering_id},
        )
    return material


def get_downloadable_file(*, actor, file_id):
    record = UploadedFile.objects.select_related("course_offering").filter(
        pk=file_id, status=UploadedFile.Status.ACTIVE
    ).first()
    if record is None or not _can_read(actor, record.course_offering):
        raise ResourceNotFoundError("File not found.")
    if normalize_role(getattr(actor, "role", None)) == "student" and not record.materials.filter(
        status=LearningMaterial.Status.ACTIVE
    ).exists():
        raise ResourceNotFoundError("File not found.")
    return record
