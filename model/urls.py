from django.urls import path

from .views import overview

app_name = "model"

urlpatterns = [
    path(
        "<uuid:model_id>/",
        overview,
        name="overview",
    ),
]
