from django.urls import path

from . import views
from . import curriculum_views
from . import carry_over_views
from . import student_course_views

app_name = "academic"

urlpatterns = [
    path("students/me/curriculum-registration/", curriculum_views.StudentCurriculumRegistrationView.as_view(), name="curriculum-registration"),
    path("admin/curriculum/<str:resource>/", curriculum_views.CurriculumConfigurationView.as_view(), name="curriculum-configuration"),
    path("admin/curricula/<uuid:pk>/publish/", curriculum_views.CurriculumPublishView.as_view(), name="curriculum-publish"),
    path("admin/semesters/<uuid:pk>/curriculum-term/", curriculum_views.SemesterCurriculumTermView.as_view(), name="semester-curriculum-term"),
    path("faculties/", views.FacultyListView.as_view(), name="faculty-list"),
    path("departments/", views.DepartmentListView.as_view(), name="department-list"),
    # Pre-authentication, read-only: the public sign-up form needs the
    # department list before an account exists.
    path(
        "departments/public/",
        views.PublicDepartmentListView.as_view(),
        name="department-public-list",
    ),
    path("departments/create/", views.DepartmentCreateView.as_view(), name="department-create"),
    path("courses/", views.CourseListView.as_view(), name="course-list"),
    path("course-offerings/", views.CourseOfferingListCreateView.as_view(), name="offering-list"),
    path("course-offerings/<uuid:pk>/", views.CourseOfferingDetailView.as_view(), name="offering-detail"),
    path(
        "course-offerings/<uuid:offering_id>/schedules/",
        views.CourseOfferingScheduleListCreateView.as_view(),
        name="offering-schedules",
    ),
    # Class definitions under an offering (API Specification §22). The write
    # half is the lecturer's "Create class" action; the read half lists the
    # definitions so the client can show what it just created. Mounted on the
    # flat api/v1/ include, which is how the client addresses it.
    path(
        "course-offerings/<uuid:offering_id>/classes/",
        views.CourseOfferingClassListCreateView.as_view(),
        name="offering-classes",
    ),
    path(
        "schedules/<uuid:pk>/",
        views.ClassScheduleDetailView.as_view(),
        name="schedule-detail",
    ),
    path("admin/stats/", views.AdminStatisticsView.as_view(), name="admin-stats"),
    path("students/me/available-courses/", views.StudentAvailableCoursesView.as_view(), name="available-courses"),
    path("students/me/register/", views.StudentRegistrationView.as_view(), name="student-register"),
    path("students/me/courses/", views.StudentMyCoursesView.as_view(), name="student-courses"),
    path("lecturers/me/courses/", views.LecturerMyCoursesView.as_view(), name="lecturer-courses"),
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
    path(
        "semesters/<uuid:pk>/activate/",
        views.SemesterActivateView.as_view(),
        name="semester-activate",
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
    # Carry-over applications. Approval by staff is what creates the
    # enrollment, so attendance eligibility follows a real review rather than
    # a self-service write. Mounted here, which the flat api/v1/ include
    # exposes as /api/v1/carry-over/ — the path the client uses.
    path(
        "carry-over/",
        carry_over_views.CarryOverListView.as_view(),
        name="carry-over-list",
    ),
    path(
        "carry-over/apply/",
        carry_over_views.CarryOverApplyView.as_view(),
        name="carry-over-apply",
    ),
    path(
        "carry-over/<uuid:pk>/review/",
        carry_over_views.CarryOverReviewView.as_view(),
        name="carry-over-review",
    ),
    # Classroom surfaces. The client addresses /classrooms/ and
    # /classrooms/available-courses/ directly, which the flat api/v1/ include
    # exposes. Both are read-only aggregations over existing models.
    path(
        "classrooms/",
        student_course_views.ClassroomListView.as_view(),
        name="classroom-list",
    ),
    path(
        "classrooms/available-courses/",
        student_course_views.ClassroomAvailableCoursesView.as_view(),
        name="classroom-available-courses",
    ),
]
