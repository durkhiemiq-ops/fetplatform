from django.urls import path

from . import views

app_name = "assessments"

urlpatterns = [
    path("", views.AssessmentListCreateView.as_view(), name="list"),
    path("<uuid:pk>/", views.AssessmentUpdateView.as_view(), name="detail"),
]
