"""Aggregated dashboard endpoint — API Specification §46.

Thin HTTP adapter over :func:`core.dashboard_service.build_dashboard`; it holds
no business rules of its own (see ``AGENTS.md``: views only translate
HTTP ↔ service).

Any authenticated user may call this, because the payload is role-selected and
every figure is computed from the caller's own records. There is no target id
in the request, so no cross-account read is expressible: a student asking for a
dashboard gets a student dashboard, and it contains only their enrollments,
their attendance, and the projects they belong to.

GET-only by construction — there is deliberately no write route, so there is no
state change and therefore no BR-210 audit entry to write.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from core.dashboard_service import build_dashboard


class DashboardView(APIView):
    """Role-aware aggregate for the signed-in user's landing page."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {"success": True, "data": build_dashboard(request.user)}
        )
