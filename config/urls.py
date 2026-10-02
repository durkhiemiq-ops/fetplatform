from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/accounts/", include("apps.accounts.urls")),
    path("api/v1/attendance/", include("apps.attendance.urls")),
    path("api/v1/academic/", include("apps.academic.urls")),
    path("api/v1/announcements/", include("apps.announcements.urls")),
    path("api/v1/assessments/", include("apps.assessments.urls")),
    path("api/v1/projects/", include("apps.projects.urls")),
    path("api/v1/notifications/", include("apps.notifications.urls")),
]
