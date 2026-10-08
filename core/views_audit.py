"""Read-only audit log API backing the admin Audit Log console.

BR-211 (audit records are protected) is enforced structurally here, not by a
permission check that could be bypassed: this module exposes GET routes only.
There is deliberately no POST/PUT/PATCH/DELETE, so modifying or deleting an
audit record is not a denied operation — it is an operation that does not
exist. The "absence is the control" principle from PRESENTATION.html applies.

Both routes are administrator-only via ``IsAdministrator``. Ordinary users
cannot list audit records either: applicant and student identity appears in
actor fields, and that is not enumerable data.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils import timezone
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AuditEvent
from core.permissions import IsAdministrator

PAGE_SIZE_DEFAULT = 20
PAGE_SIZE_MAX = 100

#: Actions counted as failed sign-ins by the console header. No writer emits
#: these yet; the counter is honest (0) rather than absent so the UI contract
#: stays stable when a writer is added.
FAILED_LOGIN_ACTIONS = frozenset({"LOGIN_FAILED", "login_failed"})


def _success(data, status=200):
    return Response({"success": True, "data": data}, status=status)


def _serialize(event, users_by_id):
    actor = users_by_id.get(str(event.actor_id))
    return {
        "id": str(event.pk),
        # The console reads `created_at`; the model stores `timestamp`.
        "created_at": event.timestamp.isoformat() if event.timestamp else None,
        "actor_full_name": (
            f"{actor.first_name} {actor.last_name}".strip() or None
            if actor is not None else None
        ),
        "actor_email": getattr(actor, "email", None),
        "action": event.action,
        "resource_type": event.resource_type,
        "resource_id": event.resource_id,
        # Actor IP is not recorded by any writer; the console renders '—'.
        # Returning the key as null keeps the row contract stable.
        "ip_address": None,
    }


def _resolve_users(actor_ids):
    model = get_user_model()
    users = model.objects.filter(pk__in=[a for a in actor_ids if a]).only(
        "first_name", "last_name", "email"
    )
    return {str(user.pk): user for user in users}


class AuditLogListView(APIView):
    """Paginated, filterable audit events, newest first. Admin-only, GET-only."""

    permission_classes = [IsAdministrator]

    def get(self, request):
        queryset = AuditEvent.objects.all().order_by("-timestamp", "-id")

        action = (request.query_params.get("action") or "").strip()
        if action:
            queryset = queryset.filter(action=action)
        resource_type = (request.query_params.get("resource_type") or "").strip()
        if resource_type:
            queryset = queryset.filter(resource_type=resource_type)
        search = (request.query_params.get("search") or "").strip()[:100]
        if search:
            queryset = queryset.filter(
                Q(action__icontains=search)
                | Q(resource_type__icontains=search)
                | Q(resource_id__icontains=search)
            )

        try:
            page_size = int(request.query_params.get("page_size", PAGE_SIZE_DEFAULT))
        except (TypeError, ValueError):
            page_size = PAGE_SIZE_DEFAULT
        page_size = min(max(page_size, 1), PAGE_SIZE_MAX)
        page = Paginator(queryset, page_size).get_page(request.query_params.get("page", 1))

        users_by_id = _resolve_users({row.actor_id for row in page.object_list})

        return _success({
            "results": [_serialize(row, users_by_id) for row in page.object_list],
            "available_actions": sorted(
                AuditEvent.objects.order_by("action").values_list("action", flat=True).distinct()
            ),
            "pagination": {
                "page": page.number,
                "total_pages": page.paginator.num_pages,
                "total": page.paginator.count,
                "page_size": page.paginator.per_page,
            },
        })


class AuditSummaryView(APIView):
    """Console header counters. Admin-only, GET-only."""

    permission_classes = [IsAdministrator]

    def get(self, request):
        since = timezone.now() - timedelta(hours=24)
        day = AuditEvent.objects.filter(timestamp__gte=since)
        return _success({
            "events_24h": day.count(),
            "failed_logins_24h": day.filter(action__in=FAILED_LOGIN_ACTIONS).count(),
            "distinct_actors_24h": day.values("actor_id").distinct().count(),
            "total_events": AuditEvent.objects.count(),
        })
