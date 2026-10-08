from django.contrib import admin
from django.urls import include, path
from apps.accounts.views import RosterUploadView
from apps.attendance.views import AttendanceRecordListView, MyStationView
from apps.academic import student_course_views
from apps.assessments import views_coursework
from core import views_audit, views_dashboard

urlpatterns = [
    path("admin/", admin.site.urls),
    # Canonical flat academic surface used by the integrated frontend. The
    # legacy /academic/ mount remains temporarily for existing clients/tests.
    path(
        "api/v1/",
        include(("apps.academic.urls", "academic_flat"), namespace="academic-flat"),
    ),
    # Student attendance surfaces live in the attendance app but share the
    # client's single /students/me/* prefix (one place for "my" data).
    path("api/v1/students/me/station/", MyStationView.as_view(), name="student-station"),
    path(
        "api/v1/students/me/attendance/",
        AttendanceRecordListView.as_view(),
        name="student-attendance",
    ),
    # The student's own released assessment results (BR-131). Registered here
    # rather than under /academic/ because the client addresses
    # /api/v1/students/me/assessments/ directly, and /academic/ cannot reach
    # that prefix. Released-only; private lecturer notes never leave.
    path(
        "api/v1/students/me/assessments/",
        student_course_views.StudentAssessmentsView.as_view(),
        name="student-assessments",
    ),
    # Coursework surface (assignments, submissions, assessment sheets/marks,
    # groups). The client addresses these under /course-offerings/*, /assignments/*
    # and /assessment-*, which the flat mount reaches. Every route is scoped to
    # the offering that owns the object; see views_coursework for the mapping.
    path(
        "api/v1/course-offerings/<str:offering_id>/assignments/",
        views_coursework.OfferingAssignmentListCreateView.as_view(),
        name="offering-assignments",
    ),
    path(
        "api/v1/course-offerings/<str:offering_id>/assessment-sheets/",
        views_coursework.OfferingSheetListCreateView.as_view(),
        name="offering-assessment-sheets",
    ),
    path(
        "api/v1/course-offerings/<str:offering_id>/assessment-groups/",
        views_coursework.OfferingGroupListCreateView.as_view(),
        name="offering-assessment-groups",
    ),
    path(
        "api/v1/assignments/<str:pk>/",
        views_coursework.AssignmentDetailView.as_view(),
        name="assignment-detail",
    ),
    path(
        "api/v1/assignments/<str:pk>/submissions/",
        views_coursework.AssignmentSubmissionListCreateView.as_view(),
        name="assignment-submissions",
    ),
    path(
        "api/v1/submissions/<str:pk>/",
        views_coursework.SubmissionDetailView.as_view(),
        name="submission-detail",
    ),
    path(
        "api/v1/assessment-sheets/<str:pk>/",
        views_coursework.SheetDetailView.as_view(),
        name="assessment-sheet-detail",
    ),
    path(
        "api/v1/assessment-sheets/<str:pk>/marks/",
        views_coursework.SheetMarksView.as_view(),
        name="assessment-sheet-marks",
    ),
    path(
        "api/v1/assessment-sheets/<str:pk>/publish/",
        views_coursework.AssessmentMarkPublishView.as_view(),
        name="assessment-sheet-publish",
    ),
    path(
        "api/v1/assessment-marks/<str:pk>/",
        views_coursework.AssessmentMarkDetailView.as_view(),
        name="assessment-mark-detail",
    ),
    path(
        "api/v1/assessment-groups/<str:pk>/",
        views_coursework.GroupDetailView.as_view(),
        name="assessment-group-detail",
    ),
    # Bulk release of every sheet in one collection (accepted decision B).
    # Mounted after the detail route: `<str:pk>` cannot contain a `/`, so the
    # two never collide, and a malformed id still resolves to the standard 404
    # envelope rather than an unrouted Django 404.
    path(
        "api/v1/assessment-groups/<str:pk>/publish/",
        views_coursework.GroupPublishView.as_view(),
        name="assessment-group-publish",
    ),
    path(
        "api/v1/students/me/assignments/",
        views_coursework.MyAssignmentsView.as_view(),
        name="my-assignments",
    ),
    # --- CSV export ---------------------------------------------------------
    # One authoritative export capability, mounted on both the canonical path
    # and the path the client already calls. Both resolve to the same view and
    # therefore to the same service function; neither has its own copy of the
    # rules. The route uses a <str:pk> converter rather than <uuid:pk>, so a
    # malformed id reaches the view and is answered with the standard 404
    # envelope instead of dying at the router as an unrouted Django 404.
    path(
        "api/v1/assessment-sheets/<str:pk>/export.csv",
        views_coursework.SheetExportView.as_view(),
        name="assessment-sheet-export",
    ),
    path(
        "api/v1/assessment-groups/<str:pk>/export.csv",
        views_coursework.GroupExportView.as_view(),
        name="assessment-group-export",
    ),
    # --- Compatibility aliases --------------------------------------------
    # The client addresses coursework sheets under /assessments/* (see
    # frontend/src/lib/learning.js). These routes exist only to catch that
    # spelling: every one of them resolves to the canonical view above, so the
    # behaviour and the service layer are shared rather than duplicated.
    # Registered before the /assessments/ include below, which is what lets
    # them win the match; the include keeps serving the released-results
    # surface exactly as before.
    path(
        "api/v1/course-offerings/<str:offering_id>/assessments/",
        views_coursework.OfferingSheetListCreateView.as_view(),
        name="offering-assessments-alias",
    ),
    path(
        "api/v1/assessments/<str:pk>/export.csv",
        views_coursework.SheetExportView.as_view(),
        name="assessment-export-alias",
    ),
    path(
        "api/v1/assessments/<str:pk>/marks/",
        views_coursework.SheetMarksView.as_view(),
        name="assessment-marks-alias",
    ),
    path(
        "api/v1/assessments/<str:pk>/",
        views_coursework.AssessmentPathAliasView.as_view(),
        name="assessment-detail-alias",
    ),
    path("api/v1/accounts/", include("apps.accounts.urls")),
    path(
        "api/v1/admin/roster/upload/",
        RosterUploadView.as_view(),
        name="roster-upload",
    ),
    # Alias for the FET-official client's /api/v1/auth/* paths. Same views.
    path("api/v1/auth/", include("apps.accounts.auth_alias_urls")),
    path("api/v1/attendance/", include("apps.attendance.urls")),
    path("api/v1/academic/", include("apps.academic.urls")),
    path("api/v1/announcements/", include("apps.announcements.urls")),
    path("api/v1/assessments/", include("apps.assessments.urls")),
    path("api/v1/projects/", include("apps.projects.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
    # Read-only audit log console (BR-211). GET-only by design: no write
    # routes exist, so audit records cannot be modified or deleted.
    # Role-aware aggregated dashboard (API Specification §46). Authenticated-
    # only; the payload is selected by the caller's own role and contains only
    # records scoped to that caller, so no target id is accepted.
    path("api/v1/dashboard/", views_dashboard.DashboardView.as_view(), name="dashboard"),
    path("api/v1/audit/logs/", views_audit.AuditLogListView.as_view(), name="audit-log-list"),
    path("api/v1/audit/summary/", views_audit.AuditSummaryView.as_view(), name="audit-summary"),
    path("api/v1/", include("apps.files.urls")),
]
