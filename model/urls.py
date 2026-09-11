from django.urls import path

from .views.overview import overview
from .views.proposal import proposal
from .views.object_types import object_types
from .views.object_type_editor import object_type_editor

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
    path(
        "<uuid:model_id>/object-types/",
        object_types,
        name="object_types",
    ),
    path(
        "<uuid:model_id>/object-types/new/",
        object_type_editor,
        name="object_type_create",
    ),
    path(
        "<uuid:model_id>/object-types/<uuid:object_type_id>/",
        object_type_editor,
        name="object_type_edit",
    ),
]
