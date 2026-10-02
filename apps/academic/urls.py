from django.urls import path

from . import views

app_name = "academic"

urlpatterns = [
    path("faculties/", views.FacultyListView.as_view(), name="faculty-list"),
    path("departments/", views.DepartmentListView.as_view(), name="department-list"),
    path("courses/", views.CourseListView.as_view(), name="course-list"),
    path("classes/", views.ClassSessionListView.as_view(), name="class-list"),
    path(
        "school-years/",
        views.SchoolYearListCreateView.as_view(),
        name="school-year-list",
    ),
    path("semesters/", views.SemesterListCreateView.as_view(), name="semester-list"),
    path(
        "semesters/<uuid:pk>/",
        views.SemesterUpdateView.as_view(),
        name="semester-detail",
    ),
    # Course enrollment (BR-010..BR-015). The service layer already existed but
    # had no HTTP surface, so the frontend's Enrol/Drop control could never
    # create an Enrollment row — and attendance eligibility depends on one.
    # MyEnrollmentsView serves GET, EnrollmentCreateView serves POST; they must
    # share the path but not be registered as duplicate patterns, or the first
    # match wins and the other method 405s.
    path("enrollments/", views.EnrollmentListCreateView.as_view(), name="enrollment-list"),
    path(
        "enrollments/<uuid:course_id>/",
        views.EnrollmentDropView.as_view(),
        name="enrollment-drop",
    ),
]
