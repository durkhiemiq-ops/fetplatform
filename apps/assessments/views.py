"""Assessment API — BR-130 to BR-132 enforced through the assessment service.

Students receive only their own released records (BR-131, with private notes
stripped); academic users manage the full set with every mutation audited
(BR-132).
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.academic_access import is_authorized_academic_user

from .models import Assessment
from .serializers import (
    AssessmentCreateSerializer,
    AssessmentSerializer,
    AssessmentUpdateSerializer,
)
from .services.assessment_service import (
    AssessmentError,
    AssessmentNotFoundError,
    UnauthorizedAssessmentActionError,
    create_assessment,
    update_assessment,
)


def _error(code, message, http_status):
    return Response(
        {"success": False, "error": {"code": code, "message": message}},
        status=http_status,
    )


def _success(data, http_status=200):
    return Response({"success": True, "data": data}, status=http_status)


class AssessmentListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        is_academic = is_authorized_academic_user(request.user)
        if is_academic:
            queryset = Assessment.objects.all()
        else:
            # BR-131: students see only their own released assessments.
            queryset = Assessment.objects.filter(student=request.user, released=True)
        queryset = queryset.select_related("student", "course", "class_session", "created_by")
        data = AssessmentSerializer(
            queryset, many=True, context={"is_academic": is_academic}
        ).data
        return _success(data)

    def post(self, request):
        serializer = AssessmentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        try:
            # BR-130: the service rejects non-academic creators.
            assessment = create_assessment(
                AssessmentModel=Assessment,
                student_id=validated["student"].pk,
                created_by=request.user,
                score=validated.get("score"),
                private_notes=validated.get("private_notes", ""),
                released=validated.get("released", False),
                course_id=validated.get("course"),
                class_id=validated.get("class_session"),
            )
        except UnauthorizedAssessmentActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except AssessmentError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        data = AssessmentSerializer(assessment, context={"is_academic": True}).data
        return _success(data, 201)


class AssessmentUpdateView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        assessment = Assessment.objects.filter(pk=pk).first()
        if assessment is None:
            return _error("NOT_FOUND", "Assessment not found.", 404)
        serializer = AssessmentUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        try:
            # BR-130/132: authorization + audit happen inside the service.
            assessment = update_assessment(
                assessment=assessment,
                actor=request.user,
                new_score=validated.get("score"),
                private_notes=validated.get("private_notes"),
                released=validated.get("released"),
            )
        except AssessmentNotFoundError as exc:
            return _error("NOT_FOUND", str(exc), 404)
        except UnauthorizedAssessmentActionError as exc:
            return _error("UNAUTHORIZED", str(exc), 403)
        except AssessmentError as exc:
            return _error("INVALID_INPUT", str(exc), 400)
        data = AssessmentSerializer(
            assessment,
            context={"is_academic": is_authorized_academic_user(request.user)},
        ).data
        return _success(data)
