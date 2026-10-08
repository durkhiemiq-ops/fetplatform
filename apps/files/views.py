from django.http import FileResponse
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.permissions import IsApprovedAcademicUser

from .serializers import (
    FileUploadSerializer,
    LearningMaterialSerializer,
    MaterialCreateSerializer,
    MaterialUpdateSerializer,
    UploadedFileSerializer,
)
from .services.file_service import (
    FileConflictError,
    FileValidationError,
    ResourceNotFoundError,
    archive_material,
    create_material,
    create_uploaded_file,
    get_downloadable_file,
    get_material,
    list_materials,
    update_material,
)


def _success(data, http_status=200):
    return Response({"success": True, "data": data}, status=http_status)


def _domain_error(exc):
    if isinstance(exc, ResourceNotFoundError):
        return Response(
            {"success": False, "error": {"code": "NOT_FOUND", "message": str(exc)}},
            status=404,
        )
    if isinstance(exc, FileConflictError):
        return Response(
            {"success": False, "error": {"code": "CONFLICT", "message": str(exc)}},
            status=409,
        )
    return Response(
        {"success": False, "error": {"code": "INVALID_FILE", "message": str(exc)}},
        status=400,
    )


class FileUploadView(APIView):
    permission_classes = [IsApprovedAcademicUser]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "file-upload"
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        serializer = FileUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_uploaded_file(
                actor=request.user,
                offering_id=serializer.validated_data["course_offering"],
                upload=serializer.validated_data["file"],
            )
        except (ResourceNotFoundError, FileValidationError) as exc:
            return _domain_error(exc)
        return _success(UploadedFileSerializer(record).data, 201)


class FileDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, file_id):
        try:
            record = get_downloadable_file(actor=request.user, file_id=file_id)
        except ResourceNotFoundError as exc:
            return _domain_error(exc)
        try:
            stream = record.file.open("rb")
        except (FileNotFoundError, OSError):
            return _domain_error(ResourceNotFoundError("File not found."))
        response = FileResponse(
            stream,
            as_attachment=True,
            filename=record.original_name,
            content_type=record.mime_type,
        )
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response


class MaterialListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        permission_classes = (
            [IsApprovedAcademicUser] if self.request.method == "POST" else self.permission_classes
        )
        return [permission() for permission in permission_classes]

    def get(self, request, offering_id):
        try:
            materials = list_materials(actor=request.user, offering_id=offering_id)
        except ResourceNotFoundError as exc:
            return _domain_error(exc)
        return _success(LearningMaterialSerializer(materials, many=True).data)

    def post(self, request, offering_id):
        serializer = MaterialCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            material = create_material(
                actor=request.user,
                offering_id=offering_id,
                **serializer.validated_data,
            )
        except (ResourceNotFoundError, FileConflictError) as exc:
            return _domain_error(exc)
        return _success(LearningMaterialSerializer(material).data, 201)


class MaterialDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        permission_classes = (
            [IsApprovedAcademicUser]
            if self.request.method in {"PATCH", "DELETE"}
            else self.permission_classes
        )
        return [permission() for permission in permission_classes]

    def get(self, request, material_id):
        try:
            material = get_material(actor=request.user, material_id=material_id)
        except ResourceNotFoundError as exc:
            return _domain_error(exc)
        return _success(LearningMaterialSerializer(material).data)

    def patch(self, request, material_id):
        serializer = MaterialUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            material = update_material(
                actor=request.user,
                material_id=material_id,
                changes=serializer.validated_data,
            )
        except ResourceNotFoundError as exc:
            return _domain_error(exc)
        return _success(LearningMaterialSerializer(material).data)

    def delete(self, request, material_id):
        try:
            material = archive_material(actor=request.user, material_id=material_id)
        except ResourceNotFoundError as exc:
            return _domain_error(exc)
        return _success({"id": str(material.id), "status": material.status})

