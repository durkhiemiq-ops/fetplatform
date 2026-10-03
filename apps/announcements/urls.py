from django.urls import path

from . import views

app_name = "announcements"

urlpatterns = [
    path("", views.AnnouncementListCreateView.as_view(), name="list"),
    path("read-state/", views.AnnouncementReadStateView.as_view(), name="read-state"),
    path("<uuid:pk>/pin/", views.AnnouncementPinView.as_view(), name="pin"),
    path("<uuid:pk>/read/", views.AnnouncementReadView.as_view(), name="read"),
    path("<uuid:pk>/readers/", views.AnnouncementReadersView.as_view(), name="readers"),
    path("<uuid:pk>/", views.AnnouncementUpdateView.as_view(), name="detail"),
]
