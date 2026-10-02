"""File business logic for uploaded academic materials and protected files.

This service intentionally keeps the logic framework-agnostic and simple. It does
not build HTTP responses or require Django request objects; instead, it validates
file metadata, access authorization, and storage constraints.

Relevant rules:
- BR-090: learning materials must belong to a valid academic context.
- BR-091: protected files require authorization.
- BR-092: private files must not be publicly accessible via permanent URLs.
- BR-093: relevant metadata must be preserved.
- BR-180: large files belong in external storage; database stores metadata.
- BR-181: protected files require authorization checks.
- BR-182: validate allowed file types.
- BR-183: enforce file size limits based on purpose and type.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, Optional, Sequence, Protocol

from core.academic_access import (
    ACADEMIC_CONTEXTS,
    SCOPE_CLASS,
    SCOPE_COURSE,
    SCOPE_DEPARTMENT,
    SCOPE_FACULTY,
    user_has_scope_access,
)
from core.common import ConfigurationError, utc_now

try:
    from django.conf import settings as django_settings
    DEFAULT_MAX_FILE_SIZE_BYTES = getattr(django_settings, "MAX_FILE_SIZE_BYTES", 25 * 1024 * 1024)
except ImportError:
    DEFAULT_MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024


class FileServiceError(ValueError):
    """Base error for file validation or access decisions."""


class InvalidAcademicContextError(FileServiceError):
    """Raised when a file is not tied to a valid academic context."""


class FileAccessDeniedError(FileServiceError):
    """Raised when a user is not allowed to access a protected file."""


class FileValidationError(FileServiceError):
    """Raised when file type or size validation fails."""


class FileRecordLike(Protocol):
    id: Any
    owner_id: Any
    academic_context_type: Any
    academic_context_id: Any
    file_name: Any
    content_type: Any
    size_bytes: Any
    is_private: Any
    storage_location: Any
    uploaded_by_id: Any
    created_at: Any
    metadata: Any

    def save(self) -> Any:
        ...


ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_TEXT_TYPES = {"text/plain", "application/pdf", "application/msword", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"}
ALLOWED_VIDEO_TYPES = {"video/mp4", "video/webm"}
ALLOWED_TYPES = ALLOWED_IMAGE_TYPES | ALLOWED_TEXT_TYPES | ALLOWED_VIDEO_TYPES


def _normalize_content_type(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _normalize_context_type(value: Any) -> str:
    if value is None:
        raise InvalidAcademicContextError("Academic context type is required")
    normalized = str(value).strip().lower()
    if normalized not in ACADEMIC_CONTEXTS:
        raise InvalidAcademicContextError(f"Unsupported academic context type: {value}")
    return normalized


def validate_file_type(file_type: Any, allowed_types: Optional[Iterable[str]] = None) -> str:
    """Validate and normalize a file type.

    Time complexity: O(1)
    Space complexity: O(1)
    """
    # BR-182: file types must be validated and allowed.
    normalized = _normalize_content_type(file_type)
    allowed = {t.lower() for t in (allowed_types or ALLOWED_TYPES)}
    if not normalized:
        raise FileValidationError("File type is required")
    if normalized not in allowed:
        raise FileValidationError(f"File type '{file_type}' is not allowed")
    return normalized


def validate_file_size(size_bytes: Any, max_size_bytes: Optional[int] = None) -> int:
    """Validate that a file size is within the configured limit."""
    # BR-183: enforce maximum file sizes according to purpose and file type.
    try:
        size = int(size_bytes)
    except (TypeError, ValueError) as exc:
        raise FileValidationError("File size must be an integer") from exc
    if size < 0:
        raise FileValidationError("File size cannot be negative")
    limit = max_size_bytes if max_size_bytes is not None else DEFAULT_MAX_FILE_SIZE_BYTES
    if size > limit:
        raise FileValidationError(f"File size exceeds the maximum of {limit} bytes")
    return size


def validate_academic_context(
    *,
    academic_context_type: Any,
    academic_context_id: Any,
    context_lookup: Optional[Any] = None,
) -> None:
    """Require the file to belong to a valid academic context.

    This is intentionally a simple guard: no hidden business logic beyond the
    rule that a file must reference a valid academic context.
    """
    # BR-090: learning materials must not exist outside a valid academic context.
    normalized = _normalize_context_type(academic_context_type)
    if academic_context_id is None:
        raise InvalidAcademicContextError("Academic context id is required")
    if context_lookup is None:
        raise InvalidAcademicContextError(
            "A context lookup is required to verify academic ownership"
        )
    try:
        exists = context_lookup(context_type=normalized, context_id=academic_context_id)
    except TypeError:
        exists = context_lookup(normalized, academic_context_id)
    if not bool(exists):
        raise InvalidAcademicContextError("Academic context does not exist")


def create_file_record(
    *,
    FileModel: type[FileRecordLike],
    owner_id: Any,
    file_name: str,
    content_type: str,
    size_bytes: Any,
    academic_context_type: Any,
    academic_context_id: Any,
    storage_location: str,
    is_private: bool = True,
    metadata: Optional[Dict[str, Any]] = None,
    context_lookup: Optional[Any] = None,
    allowed_types: Optional[Iterable[str]] = None,
    max_size_bytes: Optional[int] = None,
    actor_id: Any = None,
    upload_authorizer: Optional[Any] = None,
) -> FileRecordLike:
    """Create a file record only when the file is valid and academically scoped."""
    if FileModel is None:
        raise ConfigurationError("FileModel is required")
    if owner_id is None:
        raise FileServiceError("File owner is required")
    if actor_id is None or upload_authorizer is None:
        raise FileServiceError("An authenticated uploader and authorization check are required")
    if str(actor_id) != str(owner_id):
        raise FileServiceError("Uploader identity must match the file owner")
    try:
        authorized = upload_authorizer(
            actor_id=actor_id,
            academic_context_type=academic_context_type,
            academic_context_id=academic_context_id,
        )
    except TypeError:
        authorized = upload_authorizer(actor_id, academic_context_type, academic_context_id)
    if not bool(authorized):
        raise FileAccessDeniedError("User is not authorized to upload to this context")
    if not file_name or not str(file_name).strip():
        raise FileValidationError("File name is required")
    if not storage_location or not str(storage_location).strip():
        raise FileValidationError("Storage location is required")

    validate_academic_context(
        academic_context_type=academic_context_type,
        academic_context_id=academic_context_id,
        context_lookup=context_lookup,
    )
    normalized_type = validate_file_type(content_type, allowed_types=allowed_types)
    validated_size = validate_file_size(size_bytes, max_size_bytes=max_size_bytes)

    record = FileModel()
    if hasattr(record, "owner_id"):
        record.owner_id = owner_id
    if hasattr(record, "academic_context_type"):
        record.academic_context_type = _normalize_context_type(academic_context_type)
    if hasattr(record, "academic_context_id"):
        record.academic_context_id = academic_context_id
    if hasattr(record, "file_name"):
        record.file_name = file_name
    if hasattr(record, "content_type"):
        record.content_type = normalized_type
    if hasattr(record, "size_bytes"):
        record.size_bytes = validated_size
    if hasattr(record, "storage_location"):
        record.storage_location = storage_location
    if hasattr(record, "is_private"):
        record.is_private = bool(is_private)
    if hasattr(record, "metadata"):
        record.metadata = metadata or {}
    if hasattr(record, "uploaded_by_id"):
        record.uploaded_by_id = owner_id
    if hasattr(record, "created_at"):
        record.created_at = utc_now()
    record.save()
    return record


def user_can_access_file(
    *,
    file_record: Any,
    user: Any,
    user_course_ids: Optional[Iterable[Any]] = None,
    user_class_ids: Optional[Iterable[Any]] = None,
    user_department_id: Optional[Any] = None,
    user_faculty_id: Optional[Any] = None,
    user_roles: Optional[Sequence[str]] = None,
) -> bool:
    """Return whether a user may access a file.

    Time complexity: O(1) for direct scope checks with set membership lookups.
    Space complexity: O(1) extra, ignoring the copied sets from iterables.
    """
    # BR-091 and BR-181: authorization checks are required before access.
    if file_record is None or user is None:
        return False
    if getattr(file_record, "is_private", False) is False:
        return True

    context_type = str(getattr(file_record, "academic_context_type", "")).lower()
    context_id = getattr(file_record, "academic_context_id", None)
    if getattr(file_record, "owner_id", None) == getattr(user, "id", None):
        return True

    if context_type == SCOPE_COURSE:
        return user_has_scope_access(
            user=user,
            scope=SCOPE_COURSE,
            scope_id=context_id,
            user_course_ids=user_course_ids,
            user_class_ids=user_class_ids,
            user_department_id=user_department_id,
            user_faculty_id=user_faculty_id,
            user_roles=user_roles,
        )

    if context_type == SCOPE_CLASS:
        return user_has_scope_access(
            user=user,
            scope=SCOPE_CLASS,
            scope_id=context_id,
            user_course_ids=user_course_ids,
            user_class_ids=user_class_ids,
            user_department_id=user_department_id,
            user_faculty_id=user_faculty_id,
            user_roles=user_roles,
        )

    if context_type == SCOPE_DEPARTMENT:
        return user_has_scope_access(
            user=user,
            scope=SCOPE_DEPARTMENT,
            scope_id=context_id,
            user_course_ids=user_course_ids,
            user_class_ids=user_class_ids,
            user_department_id=user_department_id,
            user_faculty_id=user_faculty_id,
            user_roles=user_roles,
        )

    if context_type == SCOPE_FACULTY:
        return user_has_scope_access(
            user=user,
            scope=SCOPE_FACULTY,
            scope_id=context_id,
            user_course_ids=user_course_ids,
            user_class_ids=user_class_ids,
            user_department_id=user_department_id,
            user_faculty_id=user_faculty_id,
            user_roles=user_roles,
        )

    return False


def access_file(
    *,
    file_record: Any,
    user: Any,
    user_course_ids: Optional[Iterable[Any]] = None,
    user_class_ids: Optional[Iterable[Any]] = None,
    user_department_id: Optional[Any] = None,
    user_faculty_id: Optional[Any] = None,
    user_roles: Optional[Sequence[str]] = None,
) -> FileRecordLike:
    """Grant access only when the file is valid and the user is authorized."""
    # BR-091, BR-181: authorization is required before access; default deny.
    if file_record is None:
        raise FileAccessDeniedError("File not found")
    if not user_can_access_file(
        file_record=file_record,
        user=user,
        user_course_ids=user_course_ids,
        user_class_ids=user_class_ids,
        user_department_id=user_department_id,
        user_faculty_id=user_faculty_id,
        user_roles=user_roles,
    ):
        raise FileAccessDeniedError("User does not have access to this protected file")

    if getattr(file_record, "is_private", False) and not getattr(file_record, "storage_location", None):
        raise FileAccessDeniedError("Protected file record is missing an authorized storage location")

    # BR-092: private files must not be exposed via permanent unrestricted URLs.
    if getattr(file_record, "is_private", False):
        location = str(getattr(file_record, "storage_location", "")).strip()
        if location.startswith("http://") or location.startswith("https://"):
            raise FileAccessDeniedError("Private files cannot be publicly exposed through unrestricted URLs")

    return file_record


def preserve_file_metadata(
    *,
    file_record: Any,
    metadata: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Merge metadata while preserving canonical academic information."""
    # BR-093 and BR-180: metadata must remain attached even when the file itself is
    # stored outside the relational database.
    if file_record is None:
        raise FileServiceError("File record is required")
    existing = getattr(file_record, "metadata", None) or {}
    if not isinstance(existing, dict):
        existing = {}
    merged = dict(existing)
    if metadata:
        merged.update(metadata)
    file_record.metadata = merged
    file_record.save()
    return merged
