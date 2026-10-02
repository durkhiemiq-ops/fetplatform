from django.urls import path

from . import views

app_name = "projects"

urlpatterns = [
    path("", views.ProjectListCreateView.as_view(), name="list"),
    path("<uuid:pk>/", views.ProjectDetailView.as_view(), name="detail"),
    path("<uuid:pk>/groups/", views.ProjectGroupCreateView.as_view(), name="group-create"),
    path("<uuid:pk>/members/", views.ProjectMemberCreateView.as_view(), name="member-add"),
    path("<uuid:pk>/tasks/", views.ProjectTaskCreateView.as_view(), name="task-create"),
    path(
        "<uuid:pk>/contributions/",
        views.ProjectContributionCreateView.as_view(),
        name="contribution-create",
    ),
    path("tasks/<uuid:pk>/", views.TaskStatusUpdateView.as_view(), name="task-status"),
    path(
        "<uuid:pk>/milestones/",
        views.ProjectMilestoneListCreateView.as_view(),
        name="milestone-list",
    ),
    path(
        "milestones/<uuid:pk>/",
        views.ProjectMilestoneDetailView.as_view(),
        name="milestone-detail",
    ),
    path("contributions/", views.ContributionListView.as_view(), name="contribution-list"),
    path(
        "contributions/<uuid:pk>/",
        views.ContributionReviewView.as_view(),
        name="contribution-review",
    ),
]
