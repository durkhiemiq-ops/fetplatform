from django.urls import path

from . import views

app_name = "files"

urlpatterns = [
    path("files/", views.FileUploadView.as_view(), name="file-upload"),
    path("files/<uuid:file_id>/", views.FileDownloadView.as_view(), name="file-download"),
    path(
        "course-offerings/<uuid:offering_id>/materials/",
        views.MaterialListCreateView.as_view(),
        name="material-list",
    ),
    path("materials/<uuid:material_id>/", views.MaterialDetailView.as_view(), name="material-detail"),
]

