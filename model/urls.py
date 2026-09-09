from django.urls import path

from .views.overview import overview
from .views.proposal import proposal

app_name = "model"

urlpatterns = [
    path(
        "<uuid:model_id>/",
        overview,
        name="overview",
    ),
    path(
        "<uuid:model_id>/proposal/",
        proposal,
        name="proposal",
    ),
]
