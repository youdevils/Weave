"""
AppearanceService: the single API for reading, updating, resolving and pruning
a Model's visual appearance.

    Model.appearance -> AppearanceService -> resolved appearance
                                                -> UI / graph compilers / viewer adapter

The structure of ``Model.appearance`` is private to this package. Consumers
receive resolved dataclasses or the plain form structures returned by
``customisation_form`` / ``type_form``, never the stored JSON.

Appearance is deliberately outside the Proposal system: writes persist
directly. The only contact with proposals is *reading* them, to know which
proposed (not yet canonical) types may legitimately carry styles.
"""

from __future__ import annotations

import dataclasses
import uuid

from django.db import transaction

from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship_type import RelationshipType

from . import defaults, schema
from .resolved import (
    ResolvedObjectAppearance,
    ResolvedRelationshipAppearance,
    ResolvedTheme,
)
from .resolver import resolve_object, resolve_relationship, resolve_theme

OBJECT_TYPE = schema.OBJECT_TYPE
RELATIONSHIP_TYPE = schema.RELATIONSHIP_TYPE

AppearanceValidationError = schema.AppearanceValidationError


class UnknownTypeError(ValueError):
    """The id is neither a canonical type of the model nor a type proposed for it."""


_TYPE_MODELS = {
    OBJECT_TYPE: (ObjectType, "ObjectType"),
    RELATIONSHIP_TYPE: (RelationshipType, "RelationshipType"),
}

# A proposal still able to introduce a type. Completed proposals have already
# applied their changes, so their CREATEs are represented canonically (or the
# type has since been deleted).
_LIVE_PROPOSAL_STATUSES = (
    Proposal.Status.WORKING,
    Proposal.Status.QUEUED,
    Proposal.Status.PROCESSING,
    Proposal.Status.FAILED,
)


def _normalise_type_id(type_id) -> str:
    try:
        return str(uuid.UUID(str(type_id)))
    except (ValueError, AttributeError, TypeError):
        raise UnknownTypeError("Unknown type.") from None


def _check_kind(kind: str) -> None:
    if kind not in schema.TYPE_KINDS:
        raise ValueError(f"Unknown type kind: {kind}")


class AppearanceResolver:
    """Resolves appearance for many types from one read of the document."""

    def __init__(self, document: dict):
        self._document = document
        self._theme = resolve_theme(schema.model_layer(document, schema.THEME))

    @property
    def theme(self) -> ResolvedTheme:
        return self._theme

    def object_type(self, type_id) -> ResolvedObjectAppearance:
        layer = schema.type_map(self._document, OBJECT_TYPE).get(str(type_id), {})
        resolved = resolve_object(self._theme, schema.model_layer(self._document, schema.OBJECT), layer)
        if resolved.background_source != "attribute" and resolved.border_source != "attribute":
            return resolved
        return dataclasses.replace(
            resolved,
            background_by_value=(
                schema.attribute_colours(self._document, OBJECT_TYPE, type_id, resolved.background_attribute)
                if resolved.background_source == "attribute" and resolved.background_attribute
                else {}
            ),
            border_by_value=(
                schema.attribute_colours(self._document, OBJECT_TYPE, type_id, resolved.border_attribute)
                if resolved.border_source == "attribute" and resolved.border_attribute
                else {}
            ),
        )

    def relationship_type(self, type_id) -> ResolvedRelationshipAppearance:
        layer = schema.type_map(self._document, RELATIONSHIP_TYPE).get(str(type_id), {})
        resolved = resolve_relationship(
            self._theme,
            schema.model_layer(self._document, schema.RELATIONSHIP),
            layer,
        )
        if resolved.colour_source != "attribute" or not resolved.colour_attribute:
            return resolved
        return dataclasses.replace(
            resolved,
            colour_by_value=schema.attribute_colours(
                self._document, RELATIONSHIP_TYPE, type_id, resolved.colour_attribute
            ),
        )


class AppearanceService:

    # -----------------------------------------------------------------
    # Reading / resolving
    # -----------------------------------------------------------------

    @staticmethod
    def resolver(model) -> AppearanceResolver:
        """Resolver for compilers: read once, resolve many types."""
        return AppearanceResolver(schema.sanitise_document(model.appearance))

    @staticmethod
    def resolve_object_type(model, type_id) -> ResolvedObjectAppearance:
        return AppearanceService.resolver(model).object_type(type_id)

    @staticmethod
    def resolve_relationship_type(model, type_id) -> ResolvedRelationshipAppearance:
        return AppearanceService.resolver(model).relationship_type(type_id)

    @staticmethod
    def resolve_theme(model) -> ResolvedTheme:
        return AppearanceService.resolver(model).theme

    @staticmethod
    def legend(model) -> dict:
        """Swatch colours for the overview legend: model-default look plus the proposal cue."""
        resolver = AppearanceService.resolver(model)
        default_object = resolver.object_type("")
        default_edge = resolver.relationship_type("")
        return {
            "node_background": default_object.background,
            "node_border": default_object.border,
            "edge_colour": default_edge.colour,
            "proposed_colour": defaults.PROPOSED_EDGE_COLOUR,
        }

    @staticmethod
    def has_customisation(model) -> bool:
        """Whether any model-level (not per-type) customisation is set."""
        document = schema.sanitise_document(model.appearance)
        return any(schema.model_layer(document, scope) for scope in schema.SCOPES)

    @staticmethod
    def has_type_style(model, kind: str, type_id) -> bool:
        _check_kind(kind)
        document = schema.sanitise_document(model.appearance)
        return str(type_id) in schema.type_map(document, kind)

    # -----------------------------------------------------------------
    # Writing
    # -----------------------------------------------------------------

    @staticmethod
    def _mutate(model, mutate) -> dict:
        """
        Read-modify-write the document under a row lock (several editors share
        one document). Uses queryset.update so it never touches ``revision`` or
        the model's other fields.
        """
        with transaction.atomic():
            stored = (
                Model.objects.select_for_update().values_list("appearance", flat=True).get(pk=model.pk)
            )
            document = schema.sanitise_document(stored)
            mutate(document)
            Model.objects.filter(pk=model.pk).update(appearance=document)
        model.appearance = document
        return document

    @staticmethod
    def update_customisation(model, scope: str, field: str, value) -> None:
        """Set (or, for an empty value, clear) one model-level customisation."""
        if scope not in schema.SCOPES:
            raise AppearanceValidationError(f"Unknown appearance scope: {scope}")

        cleared = value is None or value == ""
        cleaned = None if cleared else schema.clean_value(scope, field, value, model_level=True)
        if cleared:
            schema.get_field(scope, field, model_level=True)  # unknown field is still an error

        def mutate(document):
            layer = schema.model_layer(document, scope)
            if cleared:
                layer.pop(field, None)
            else:
                layer[field] = cleaned

        AppearanceService._mutate(model, mutate)

    @staticmethod
    def reset_customisation(model) -> None:
        """
        Clear model-level customisation only. Per-type overrides are managed
        independently by the type editors and are left untouched.
        """

        def mutate(document):
            for scope in schema.SCOPES:
                schema.model_layer(document, scope).clear()

        AppearanceService._mutate(model, mutate)

    # The attribute-selecting fields whose *value* must additionally be one of
    # the type's current eligible (Choice/Boolean, canonical-or-proposed)
    # attribute keys -- a check schema.py cannot make on its own since it has
    # no DB/proposal access and eligibility is dynamic per type.
    _ATTRIBUTE_SELECT_FIELDS = ("background_attribute", "border_attribute", "colour_attribute")

    @staticmethod
    def set_type_style(model, kind: str, type_id, field: str, value, *, valid_attribute_keys=None) -> None:
        """
        Set (or, for an empty value, clear) one field of a type's override.

        ``valid_attribute_keys``, when given, additionally restricts a
        ``background_attribute``/``border_attribute``/``colour_attribute``
        value to that set (the caller's current eligible-attribute list); it
        is ignored for every other field.
        """
        _check_kind(kind)
        type_key = _normalise_type_id(type_id)
        if not AppearanceService.is_known_type(model, kind, type_key):
            raise UnknownTypeError("Unknown type.")

        scope = schema.KIND_SCOPE[kind]
        cleared = value is None or value == ""
        cleaned = None if cleared else schema.clean_value(scope, field, value)
        if cleared:
            schema.get_field(scope, field)
        if (
            not cleared
            and valid_attribute_keys is not None
            and field in AppearanceService._ATTRIBUTE_SELECT_FIELDS
            and cleaned not in valid_attribute_keys
        ):
            raise AppearanceValidationError("That attribute is not available for this type.")

        def mutate(document):
            entries = schema.type_map(document, kind)
            layer = entries.setdefault(type_key, {})
            if cleared:
                layer.pop(field, None)
            else:
                layer[field] = cleaned
            if not layer:
                entries.pop(type_key, None)

        AppearanceService._mutate(model, mutate)

    @staticmethod
    def clear_type_style(model, kind: str, type_id, field: str | None = None) -> None:
        """Remove one override field, or all of a type's overrides when ``field`` is None."""
        if field is not None:
            AppearanceService.set_type_style(model, kind, type_id, field, None)
            return

        _check_kind(kind)
        type_key = _normalise_type_id(type_id)

        def mutate(document):
            schema.type_map(document, kind).pop(type_key, None)

        AppearanceService._mutate(model, mutate)

    # -----------------------------------------------------------------
    # Choice / Boolean attribute value colours
    #
    # Independent of whether the attribute is currently selected as a
    # background/border/line colour source (requirement: these colours exist
    # regardless, configured directly on the attribute).
    # -----------------------------------------------------------------

    @staticmethod
    def attribute_value_colours(model, kind: str, type_id, attribute_key: str) -> dict:
        """The value->hex colour map configured for one attribute of one type."""
        _check_kind(kind)
        document = schema.sanitise_document(model.appearance)
        return dict(schema.attribute_colours(document, kind, type_id, attribute_key))

    @staticmethod
    def set_attribute_colour(model, kind: str, type_id, attribute_key: str, value_key: str, colour) -> None:
        """Set (or, for an empty colour, clear) one attribute value's colour."""
        _check_kind(kind)
        type_key = _normalise_type_id(type_id)
        if not attribute_key or not value_key:
            raise AppearanceValidationError("An attribute and value are required.")

        cleared = colour is None or colour == ""
        cleaned = None if cleared else schema.clean_colour_value(f"{attribute_key} colour", colour)

        def mutate(document):
            by_kind = schema.attribute_colour_map(document, kind)
            by_type = by_kind.setdefault(type_key, {})
            by_attribute = by_type.setdefault(attribute_key, {})
            if cleared:
                by_attribute.pop(value_key, None)
            else:
                by_attribute[value_key] = cleaned
            if not by_attribute:
                by_type.pop(attribute_key, None)
            if not by_type:
                by_kind.pop(type_key, None)

        AppearanceService._mutate(model, mutate)

    @staticmethod
    def clear_attribute_colour(model, kind: str, type_id, attribute_key: str, value_key: str | None = None) -> None:
        """Remove one value's colour, or every colour configured for the attribute when ``value_key`` is None."""
        if value_key is not None:
            AppearanceService.set_attribute_colour(model, kind, type_id, attribute_key, value_key, None)
            return

        _check_kind(kind)
        type_key = _normalise_type_id(type_id)

        def mutate(document):
            by_type = schema.attribute_colour_map(document, kind).get(type_key)
            if by_type is not None:
                by_type.pop(attribute_key, None)
                if not by_type:
                    schema.attribute_colour_map(document, kind).pop(type_key, None)

        AppearanceService._mutate(model, mutate)

    # -----------------------------------------------------------------
    # Type lifecycle
    # -----------------------------------------------------------------

    @staticmethod
    def _canonical_ids(model, kind: str) -> set[str]:
        model_cls, _target = _TYPE_MODELS[kind]
        return {str(pk) for pk in model_cls.objects.filter(model=model).values_list("id", flat=True)}

    @staticmethod
    def _live_proposed_ids(model, kind: str) -> set[str]:
        _model_cls, target = _TYPE_MODELS[kind]
        return {
            str(pk)
            for pk in ProposalChange.objects.filter(
                proposal__model=model,
                proposal__status__in=_LIVE_PROPOSAL_STATUSES,
                operation=ProposalChange.Operation.CREATE,
                target_type=target,
            )
            .exclude(target_id=None)
            .values_list("target_id", flat=True)
        }

    @staticmethod
    def is_known_type(model, kind: str, type_id) -> bool:
        """A canonical type of this model, or one proposed for it by a live proposal."""
        _check_kind(kind)
        try:
            type_key = str(uuid.UUID(str(type_id)))
        except (ValueError, AttributeError, TypeError):
            return False

        model_cls, target = _TYPE_MODELS[kind]
        if model_cls.objects.filter(model=model, id=type_key).exists():
            return True
        return ProposalChange.objects.filter(
            proposal__model=model,
            proposal__status__in=_LIVE_PROPOSAL_STATUSES,
            operation=ProposalChange.Operation.CREATE,
            target_type=target,
            target_id=type_key,
        ).exists()

    @staticmethod
    def prune(model) -> None:
        """
        Drop type styles whose type no longer exists anywhere: not canonical, and
        not proposed by any live proposal. Idempotent; call after a proposal is
        abandoned, a proposed type is discarded, or a proposal is applied.
        """

        def mutate(document):
            for kind in schema.TYPE_KINDS:
                entries = schema.type_map(document, kind)
                if not entries:
                    continue
                keep = AppearanceService._canonical_ids(model, kind) | AppearanceService._live_proposed_ids(
                    model, kind
                )
                for type_key in [key for key in entries if key not in keep]:
                    del entries[type_key]

        AppearanceService._mutate(model, mutate)

    # -----------------------------------------------------------------
    # Form structures for the shared UI (plain data, not the stored JSON)
    # -----------------------------------------------------------------

    @staticmethod
    def customisation_form(model) -> dict:
        document = schema.sanitise_document(model.appearance)
        theme_layer = schema.model_layer(document, schema.THEME)
        object_layer = schema.model_layer(document, schema.OBJECT)
        relationship_layer = schema.model_layer(document, schema.RELATIONSHIP)
        theme = resolve_theme(theme_layer)

        def resolve_theme_layer(layer):
            return resolve_theme(layer).to_dict()

        def resolve_object_layer(layer):
            return resolve_object(theme, layer, {}).to_dict()

        def resolve_relationship_layer(layer):
            return resolve_relationship(theme, layer, {}).to_dict()

        return {
            "scopes": [
                {
                    "scope": schema.THEME,
                    "title": "Theme",
                    "description": "Colours and typography shared by every graph in this model.",
                    "groups": _groups(schema.THEME, theme_layer, resolve_theme_layer, model_level=True),
                },
                {
                    "scope": schema.OBJECT,
                    "title": "Object Types",
                    "description": "Defaults for every Object Type. A type's own style overrides these.",
                    "groups": _groups(schema.OBJECT, object_layer, resolve_object_layer, model_level=True),
                },
                {
                    "scope": schema.RELATIONSHIP,
                    "title": "Relationship Types",
                    "description": "Defaults for every Relationship Type. A type's own style overrides these.",
                    "groups": _groups(
                        schema.RELATIONSHIP, relationship_layer, resolve_relationship_layer, model_level=True
                    ),
                },
            ],
            "has_customisation": any((theme_layer, object_layer, relationship_layer)),
            "canvas_background": theme.canvas_background,
        }

    @staticmethod
    def type_form(model, kind: str, type_id, eligible_attributes=()) -> dict:
        """
        ``eligible_attributes`` is ``[(key, name), ...]`` for this type's
        current Choice/Boolean effective attributes (canonical or introduced/
        changed by the active proposal) -- the caller resolves this via
        ``model.views.data_context.build_object_attribute_definitions`` /
        ``build_relationship_attribute_definitions``, since this service has
        no proposal/attribute-definition access of its own.
        """
        _check_kind(kind)
        scope = schema.KIND_SCOPE[kind]
        type_key = str(type_id)
        document = schema.sanitise_document(model.appearance)
        theme = resolve_theme(schema.model_layer(document, schema.THEME))
        model_layer = schema.model_layer(document, scope)
        layer = schema.type_map(document, kind).get(type_key, {})

        if scope == schema.OBJECT:

            def resolve_layer(candidate):
                return resolve_object(theme, model_layer, candidate).to_dict()

        else:

            def resolve_layer(candidate):
                return resolve_relationship(theme, model_layer, candidate).to_dict()

        return {
            "kind": kind,
            "type_id": type_key,
            "groups": _groups(scope, layer, resolve_layer, model_level=False, eligible_attributes=eligible_attributes),
            "has_overrides": bool(layer),
            "text_inside_shapes": list(schema.TEXT_INSIDE_SHAPES),
        }


def _groups(scope: str, layer: dict, resolve_layer, *, model_level: bool, eligible_attributes=()) -> list[dict]:
    """Field states for one scope, grouped in spec order."""
    current = resolve_layer(layer)
    groups: dict[str, list] = {}
    eligible_keys = {key for key, _name in eligible_attributes}

    for spec in schema.field_specs(scope, model_level=model_level):
        without = {key: value for key, value in layer.items() if key != spec.key}
        inherited = resolve_layer(without).get(spec.key)
        value = current.get(spec.key)
        field = spec.to_dict()
        field.update(
            value="" if value is None else value,
            inherited="" if inherited is None else inherited,
            overridden=spec.key in layer,
        )
        if spec.control == "attribute":
            choices = [{"value": key, "label": name} for key, name in eligible_attributes]
            # The configured attribute may no longer be eligible (deactivated,
            # deleted, or its proposal discarded). Keep it selectable and
            # visibly distinct rather than silently dropping it -- colour
            # resolution already falls back to the type colour on its own,
            # but the editor should make clear *why*.
            if value and value not in eligible_keys:
                choices.append({"value": value, "label": f"{value} (no longer available)"})
            field["choices"] = choices
        groups.setdefault(spec.group, []).append(field)

    return [{"label": label, "fields": fields} for label, fields in groups.items()]


