from django.urls import path

from .views.overview import overview
from .views.proposal import proposal
from .views.object_types import object_types
from .views.object_type_editor import object_type_editor
from .views.relationship_types import relationship_types

from .views.relationship_type_editor import relationship_type_editor

app_name = "model"


urlpatterns = [
    # ================================================================
    # Model overview
    # ================================================================
    path(
        "<uuid:model_id>/",
        overview,
        name="overview",
    ),
    # ================================================================
    # Proposal review
    # ================================================================
    path(
        "<uuid:model_id>/proposal/",
        proposal,
        name="proposal",
    ),
    # ================================================================
    # Object Types
    # ================================================================
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
    # ================================================================
    # Relationship Types
    # ================================================================
    path(
        "<uuid:model_id>/relationship-types/",
        relationship_types,
        name="relationship_types",
    ),
    path(
        "<uuid:model_id>/relationship-types/new/",
        relationship_type_editor,
        name="relationship_type_create",
    ),
    path(
        "<uuid:model_id>/relationship-types/<uuid:relationship_type_id>/",
        relationship_type_editor,
        name="relationship_type_edit",
    ),
]
