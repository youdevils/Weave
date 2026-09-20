from django.urls import path
from .views import views

app_name = "workspace"

urlpatterns = [
    path("", views.index, name="index"),
    path("create-model", views.create_model, name="create_model"),
    path(
        "create-model/<uuid:model_id>/starting-point",
        views.model_starting_point,
        name="model_starting_point",
    ),
    path(
        "create-model/<uuid:model_id>/review/<str:template_key>",
        views.model_template_review,
        name="model_template_review",
    ),
    path(
        "models/<uuid:model_id>/delete",
        views.delete_model_view,
        name="delete_model",
    ),
]
