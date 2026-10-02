from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("csrf/", views.csrf_token_view, name="csrf_token"),
    path("register/", views.RegisterView.as_view(), name="register"),
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
