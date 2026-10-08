from django.urls import path

from .views import (
    AttendanceCheckpointDeleteView,
    AttendanceCheckpointSelectView,
    AttendanceCheckpointTokenView,
    AttendanceCorrectionView,
    AttendanceRecordListView,
    AttendanceReviewView,
    AttendanceScanView,
    AttendanceSessionCloseView,
    AttendanceSessionDetailView,
    AttendanceSessionListCreateView,
    AttendanceSessionTokenView,
    AttendanceAutoSelectView,
    AttendanceStationTokenView,
    FlexibleAttendanceStartView,
    MyStationView,
)

app_name = "attendance"

urlpatterns = [
    path("scan/", AttendanceScanView.as_view(), name="scan"),
    path("start-flex/", FlexibleAttendanceStartView.as_view(), name="start-flex"),
    path("sessions/", AttendanceSessionListCreateView.as_view(), name="session-list"),
    path("sessions/<uuid:pk>/", AttendanceSessionDetailView.as_view(), name="session-detail"),
    path("sessions/<uuid:pk>/close/", AttendanceSessionCloseView.as_view(), name="session-close"),
    path(
        "sessions/<uuid:pk>/token/",
        AttendanceSessionTokenView.as_view(),
        name="session-token",
    ),
    path(
        "sessions/<uuid:pk>/my-station-token/",
        AttendanceStationTokenView.as_view(),
        name="my-station-token",
    ),
    path(
        "sessions/<uuid:pk>/checkpoints/",
        AttendanceCheckpointSelectView.as_view(),
        name="session-checkpoints",
    ),
    path(
        "sessions/<uuid:pk>/checkpoints/auto-select/",
        AttendanceAutoSelectView.as_view(),
        name="session-checkpoints-auto-select",
    ),
    path(
        "sessions/<uuid:pk>/checkpoints/<uuid:checkpoint_pk>/",
        AttendanceCheckpointDeleteView.as_view(),
        name="session-checkpoint-delete",
    ),
    path(
        "checkpoints/<uuid:pk>/token/",
        AttendanceCheckpointTokenView.as_view(),
        name="checkpoint-token",
    ),
    path("records/", AttendanceRecordListView.as_view(), name="record-list"),
    path("records/<uuid:pk>/corrections/", AttendanceCorrectionView.as_view(), name="record-corrections"),
    path("records/<uuid:pk>/", AttendanceCorrectionView.as_view(), name="record-detail"),
    # Flat aliases kept for the integrated client's /attendance/<id>/ calls.
    path("<uuid:pk>/", AttendanceSessionDetailView.as_view(), name="flat-session-detail"),
    path("<uuid:pk>/close/", AttendanceSessionCloseView.as_view(), name="flat-session-close"),
    path("<uuid:pk>/token/", AttendanceSessionTokenView.as_view(), name="flat-session-token"),
    path(
        "<uuid:pk>/my-station-token/",
        AttendanceStationTokenView.as_view(),
        name="flat-my-station-token",
    ),
    path(
        "<uuid:pk>/checkpoints/",
        AttendanceCheckpointSelectView.as_view(),
        name="flat-session-checkpoints",
    ),
    path(
        "<uuid:pk>/checkpoints/auto-select/",
        AttendanceAutoSelectView.as_view(),
        name="flat-session-checkpoints-auto-select",
    ),
    path(
        "<uuid:pk>/checkpoints/<uuid:checkpoint_pk>/",
        AttendanceCheckpointDeleteView.as_view(),
        name="flat-session-checkpoint-delete",
    ),
    path("review/", AttendanceReviewView.as_view(), name="review"),
    # Student-facing surfaces. They are exported from this app because they are
    # attendance data, and mounted at /students/me/* by the root URLconf so the
    # client has one stable /students/me/* prefix (see config/urls.py).
    path("my-station/", MyStationView.as_view(), name="my-station"),
    path("my-history/", AttendanceRecordListView.as_view(), name="my-history"),
]
