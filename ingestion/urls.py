from django.urls import path

from . import views

app_name = "ingestion"

urlpatterns = [
    path("<uuid:model_id>/assets/", views.assets, name="assets"),
    path("<uuid:model_id>/assets/export/", views.export_model, name="export_model"),
    path(
        "<uuid:model_id>/assets/templates/<str:kind>/<uuid:type_id>/<str:file_format>/",
        views.download_template,
        name="download_template",
    ),
    path(
        "<uuid:model_id>/assets/templates/zip/<str:file_format>/",
        views.download_templates_zip,
        name="download_templates_zip",
    ),
    path("<uuid:model_id>/assets/import/upload/", views.import_upload, name="import_upload"),
    path("<uuid:model_id>/assets/import/preview/", views.import_preview, name="import_preview"),
    path("<uuid:model_id>/assets/import/create/", views.import_create, name="import_create"),
    path("<uuid:model_id>/assets/import/discard/", views.import_discard, name="import_discard"),
]
