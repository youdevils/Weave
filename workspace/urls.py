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
]
