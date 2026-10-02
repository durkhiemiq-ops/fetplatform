from django.urls import path

from . import views
from .views import (
    NotificationReadAllView,
    NotificationReadView,
)

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("<uuid:pk>/read/", NotificationReadView.as_view(), name="read"),
    path("read-all/", NotificationReadAllView.as_view(), name="read-all"),
]