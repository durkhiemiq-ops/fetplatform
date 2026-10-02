from django.urls import path

from .views import (
    AttendanceCheckpointSelectView,
    AttendanceCheckpointTokenView,
    AttendanceCorrectionView,
    AttendanceRecordListView,
    AttendanceReviewView,
    AttendanceScanView,
    AttendanceSessionCloseView,
    AttendanceSessionDetailView,
    AttendanceSessionListCreateView,
)

app_name = "attendance"

urlpatterns = [
    path("scan/", AttendanceScanView.as_view(), name="scan"),
    path("sessions/", AttendanceSessionListCreateView.as_view(), name="session-list"),
    path("sessions/<uuid:pk>/", AttendanceSessionDetailView.as_view(), name="session-detail"),
    path("sessions/<uuid:pk>/close/", AttendanceSessionCloseView.as_view(), name="session-close"),
    path("sessions/<uuid:pk>/checkpoints/", AttendanceCheckpointSelectView.as_view(), name="session-checkpoints"),
    path("checkpoints/<uuid:pk>/token/", AttendanceCheckpointTokenView.as_view(), name="checkpoint-token"),
    path("records/", AttendanceRecordListView.as_view(), name="record-list"),
    path("records/<uuid:pk>/corrections/", AttendanceCorrectionView.as_view(), name="record-corrections"),
    path("review/", AttendanceReviewView.as_view(), name="review"),
]