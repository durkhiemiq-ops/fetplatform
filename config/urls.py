from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    # Canonical flat academic surface used by the integrated frontend. The
    # legacy /academic/ mount remains temporarily for existing clients/tests.
    path(
        "api/v1/",
        include(("apps.academic.urls", "academic_flat"), namespace="academic-flat"),
    ),
    path("api/v1/accounts/", include("apps.accounts.urls")),
    # Alias for the FET-official client's /api/v1/auth/* paths. Same views.
    path("api/v1/auth/", include("apps.accounts.auth_alias_urls")),
    path("api/v1/attendance/", include("apps.attendance.urls")),
    path("api/v1/academic/", include("apps.academic.urls")),
    path("api/v1/announcements/", include("apps.announcements.urls")),
    path("api/v1/assessments/", include("apps.assessments.urls")),
    path("api/v1/projects/", include("apps.projects.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
]
