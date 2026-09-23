from django.urls import path

from .views.overview import overview
from .views.customise import customise
from .views.explore import (
    explore,
    explore_graph,
    explore_object,
    explore_relationship,
    explore_search,
)
from .views.appearance import attribute_value_appearance, type_appearance
from .views.proposal import proposal, proposal_create
from .views.object_types import object_types
from .views.object_type_editor import object_type_editor
from .views.relationship_types import relationship_types

from .views.relationship_type_editor import relationship_type_editor
from .views.data_objects import data_object_types, data_objects
from .views.data_object_editor import data_object_editor
from .views.data_relationships import data_relationship_types, data_relationships
from .views.data_relationship_editor import data_relationship_editor

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
    # Explore (read-only Model Explorer)
    # ================================================================
    path(
        "<uuid:model_id>/explore/",
        explore,
        name="explore",
    ),
    path(
        "<uuid:model_id>/explore/graph/",
        explore_graph,
        name="explore_graph",
    ),
    path(
        "<uuid:model_id>/explore/search/",
        explore_search,
        name="explore_search",
    ),
    path(
        "<uuid:model_id>/explore/object/<uuid:object_id>/",
        explore_object,
        name="explore_object",
    ),
    path(
        "<uuid:model_id>/explore/relationship/<uuid:relationship_id>/",
        explore_relationship,
        name="explore_relationship",
    ),
    # ================================================================
    # Customise (model-wide visual language; direct save, no proposals)
    # ================================================================
    path(
        "<uuid:model_id>/customise/",
        customise,
        name="customise",
    ),
    # ================================================================
    # Proposals
    # ================================================================
    path(
        "<uuid:model_id>/proposals/",
        proposal,
        name="proposal_list",
    ),
    path(
        "<uuid:model_id>/proposals/new/",
        proposal_create,
        name="proposal_create",
    ),
    path(
        "<uuid:model_id>/proposals/<uuid:proposal_id>/",
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
    path(
        "<uuid:model_id>/object-types/<uuid:type_id>/appearance/",
        type_appearance,
        {"kind": "object_type"},
        name="object_type_appearance",
    ),
    path(
        "<uuid:model_id>/object-types/<uuid:type_id>/attributes/<slug:attribute_key>/colours/",
        attribute_value_appearance,
        {"kind": "object_type"},
        name="object_type_attribute_colours",
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
    path(
        "<uuid:model_id>/relationship-types/<uuid:type_id>/appearance/",
        type_appearance,
        {"kind": "relationship_type"},
        name="relationship_type_appearance",
    ),
    path(
        "<uuid:model_id>/relationship-types/<uuid:type_id>/attributes/<slug:attribute_key>/colours/",
        attribute_value_appearance,
        {"kind": "relationship_type"},
        name="relationship_type_attribute_colours",
    ),
    # ================================================================
    # Data — Objects
    # ================================================================
    path(
        "<uuid:model_id>/data/objects/",
        data_object_types,
        name="data_object_types",
    ),
    path(
        "<uuid:model_id>/data/objects/<uuid:object_type_id>/",
        data_objects,
        name="data_objects",
    ),
    path(
        "<uuid:model_id>/data/objects/<uuid:object_type_id>/new/",
        data_object_editor,
        name="data_object_create",
    ),
    path(
        "<uuid:model_id>/data/objects/<uuid:object_type_id>/<uuid:object_id>/",
        data_object_editor,
        name="data_object_edit",
    ),
    # ================================================================
    # Data — Relationships
    # ================================================================
    path(
        "<uuid:model_id>/data/relationships/",
        data_relationship_types,
        name="data_relationship_types",
    ),
    path(
        "<uuid:model_id>/data/relationships/<uuid:relationship_type_id>/",
        data_relationships,
        name="data_relationships",
    ),
    path(
        "<uuid:model_id>/data/relationships/<uuid:relationship_type_id>/new/",
        data_relationship_editor,
        name="data_relationship_create",
    ),
    path(
        "<uuid:model_id>/data/relationships/<uuid:relationship_type_id>/<uuid:relationship_id>/",
        data_relationship_editor,
        name="data_relationship_edit",
    ),
]
