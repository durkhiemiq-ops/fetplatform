"""HTTP translation only; academic decisions remain in curriculum_service."""

from rest_framework.exceptions import NotFound
from rest_framework.pagination import LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.permissions import IsAdministrator

from .curriculum_serializers import (
    CONFIG_SERIALIZERS, CurriculumCompletionSerializer, CurriculumSerializer,
    EmptyInputSerializer, SemesterTermSerializer,
)
from .services import curriculum_service as service


def _success(data, status=200):
    return Response({"success": True, "data": data}, status=status)


class CurriculumErrorsMixin:
    def handle_exception(self, exc):
        if isinstance(exc, service.CurriculumError):
            return Response(
                {"success": False, "error": {"code": exc.code, "message": str(exc)}},
                status=exc.status,
            )
        return super().handle_exception(exc)


class StudentCurriculumRegistrationView(CurriculumErrorsMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return _success(service.registration_state(actor=request.user))

    def post(self, request):
        serializer = CurriculumCompletionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return _success(service.complete_registration(actor=request.user, **serializer.validated_data))


class CurriculumConfigurationView(CurriculumErrorsMixin, APIView):
    permission_classes = [IsAdministrator]

    def _serializer(self, resource):
        serializer = CONFIG_SERIALIZERS.get(resource)
        if serializer is None:
            raise NotFound()
        return serializer

    def get(self, request, resource):
        serializer = self._serializer(resource)
        pagination = LimitOffsetPagination()
        pagination.default_limit = 100
        pagination.max_limit = 200
        rows = pagination.paginate_queryset(serializer.Meta.model.objects.order_by("pk"), request, view=self)
        return _success({
            "results": serializer(rows, many=True).data,
            "count": pagination.count,
            "next": pagination.get_next_link(),
            "previous": pagination.get_previous_link(),
        })

    def post(self, request, resource):
        serializer_class = self._serializer(resource)
        serializer = serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        obj = service.create_configuration(actor=request.user, resource=resource, data=serializer.validated_data)
        return _success(serializer_class(obj).data, status=201)


class CurriculumPublishView(CurriculumErrorsMixin, APIView):
    permission_classes = [IsAdministrator]

    def post(self, request, pk):
        serializer = EmptyInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        curriculum = service.publish_curriculum(actor=request.user, curriculum_id=pk)
        return _success(CurriculumSerializer(curriculum).data)


class SemesterCurriculumTermView(CurriculumErrorsMixin, APIView):
    permission_classes = [IsAdministrator]

    def put(self, request, pk):
        serializer = SemesterTermSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        semester = service.assign_semester_term(actor=request.user, semester_id=pk, **serializer.validated_data)
        return _success({"semester": str(semester.pk), "academic_term": str(semester.academic_term_id)})
