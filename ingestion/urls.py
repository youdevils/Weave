from django.urls import path

from . import views

app_name = "ingestion"

urlpatterns = [
    path("<uuid:model_id>/assets/", views.assets, name="assets"),
    path("<uuid:model_id>/assets/import/upload/", views.import_upload, name="import_upload"),
    path("<uuid:model_id>/assets/import/preview/", views.import_preview, name="import_preview"),
    path("<uuid:model_id>/assets/import/create/", views.import_create, name="import_create"),
    path("<uuid:model_id>/assets/import/discard/", views.import_discard, name="import_discard"),
]
