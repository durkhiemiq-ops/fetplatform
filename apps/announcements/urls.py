from django.urls import path

from . import views

app_name = "announcements"

urlpatterns = [
    path("", views.AnnouncementListCreateView.as_view(), name="list"),
    path("<uuid:pk>/", views.AnnouncementUpdateView.as_view(), name="detail"),
]
