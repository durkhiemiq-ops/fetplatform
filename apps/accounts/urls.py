from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("csrf/", views.csrf_token_view, name="csrf_token"),
    # Public self-registration. Student accounts are created STUDENT
    # server-side; lecturer applicants are created PENDING and gain teaching
    # privileges only after an administrator approves them.
    path("register/", views.SelfRegisterView.as_view(), name="register"),
    path("self-register/", views.SelfRegisterView.as_view(), name="self-register"),
    path(
        "lecturers/<uuid:pk>/approval/",
        views.LecturerApprovalView.as_view(),
        name="lecturer-approval",
    ),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.CurrentUserView.as_view(), name="current-user"),
    path("change-role/", views.ChangeRoleView.as_view(), name="change-role"),
    path("verify-email/", views.VerifyEmailView.as_view(), name="verify-email"),
    path(
        "resend-verification/",
        views.ResendVerificationView.as_view(),
        name="resend-verification",
    ),
    path("students/", views.StudentListView.as_view(), name="student-list"),
    path("", views.UserListView.as_view(), name="user-list"),
]
