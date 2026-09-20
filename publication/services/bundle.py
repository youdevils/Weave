"""
The portable bundle: everything a published Explorer needs, as plain JSON.

    published dataset (Python, authoritative)  ->  bundle  ->  preview JSON / embedded in the HTML file

The bundle is the only contract between publication *building* (server side)
and the portable Explorer *runtime* (browser side). It contains no reference to
Weave: no URLs, no ids of proposals, no model or workspace ids.

What is deliberately frozen into it at publish time:
  * the published dataset (already scoped and canonical-only);
  * every type's resolved visual style (appearance is not versioned with the
    model revision, so it is resolved now rather than looked up later);
  * the filter facets and per-record provenance of the published records only.

``digest`` covers exactly that content (not the publication's own title,
timestamps or opening view), so a preview and a publish of the same content
have the same digest, and any change to the content changes it.
"""

from __future__ import annotations

import hashlib
import json

from model.services.appearance import AppearanceService
from model.services.appearance.viewer_adapter import edge_style, node_style
from model.services.model_graph.facets import build_facets
from model.services.model_graph.provenance import build_provenance_bulk
from viewer.contracts import (
    SCHEMA_VERSION,
    LayoutConfig,
    PhysicsConfig,
    StabilisationConfig,
    TypeMetadata,
    ViewerConfig,
    ViewerMetadata,
    ViewerPayload,
)

from ..models import Publication

FORMAT = "weave-portable-explorer"

# Shown for a relationship's endpoint that is not part of the publication.
OUTSIDE_PUBLICATION = "an object outside this publication"


def _attribute_specs(specs) -> list[dict]:
    return [
        {"key": s.key, "name": s.name, "dataType": s.data_type, "choices": list(s.choices)} for s in specs
    ]


def _provenance_specs(specs) -> dict:
    return {s.key: {"label": s.name, "dataType": s.data_type} for s in specs}


def _rule(rule) -> dict:
    return {
        "subjectTypeId": rule.subject_type_id,
        "objectTypeId": rule.object_type_id,
        "subjectMinimum": rule.subject_minimum,
        "subjectMaximum": rule.subject_maximum,
        "objectMinimum": rule.object_minimum,
        "objectMaximum": rule.object_maximum,
    }


def _graph_template(title, description, canvas_background, dataset) -> dict:
    """A ViewerPayload with no nodes/edges: the fixed parts the runtime fills in."""
    return ViewerPayload(
        schema_version=SCHEMA_VERSION,
        metadata=ViewerMetadata(title=title, description=description, source="publication.portable"),
        viewer_config=ViewerConfig(
            layout=LayoutConfig(mode="standard"),
            physics=PhysicsConfig(
                enabled=True,
                solver="forceAtlas2Based",
                stabilisation=StabilisationConfig(enabled=True, fit=True),
            ),
            extra={"canvas_background": canvas_background},
        ),
        node_types=[TypeMetadata(key=t.key, label=t.name) for t in dataset.object_types.values()],
        edge_types=[TypeMetadata(key=t.key, label=t.name) for t in dataset.relationship_types.values()],
    ).to_dict()


def _provenance(model, dataset) -> dict:
    names = {object_id: obj.name for object_id, obj in dataset.objects.items()}

    object_chains = build_provenance_bulk(
        model,
        "Object",
        list(dataset.objects),
        lambda object_id: _provenance_specs(dataset.object_types[dataset.objects[object_id].type_id].attributes),
        endpoint_names=names,
        missing_endpoint=OUTSIDE_PUBLICATION,
    )
    relationship_chains = build_provenance_bulk(
        model,
        "Relationship",
        list(dataset.relationships),
        lambda relationship_id: _provenance_specs(
            dataset.relationship_types[dataset.relationships[relationship_id].type_id].attributes
        ),
        endpoint_names=names,
        missing_endpoint=OUTSIDE_PUBLICATION,
    )

    # Records with no history are simply absent; the runtime treats absence as "none".
    return {
        "objects": {k: v for k, v in object_chains.items() if v["entries"]},
        "relationships": {k: v for k, v in relationship_chains.items() if v["entries"]},
    }


def canonical_json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def compute_digest(bundle: dict) -> str:
    """sha256 of the bundle's *content* (independent of title, dates, opening view, theme colour)."""
    content = {
        "formatVersion": bundle["formatVersion"],
        "sourceRevision": bundle["sourceRevision"],
        "canvasBackground": bundle["presentation"]["canvasBackground"],
        "fontFamily": bundle["presentation"]["fontFamily"],
        "dataset": bundle["dataset"],
        "facets": bundle["facets"],
        "provenance": bundle["provenance"],
    }
    return hashlib.sha256(canonical_json(content).encode("utf-8")).hexdigest()


def build_dataset_block(dataset, resolver) -> dict:
    """The bundle's ``dataset``: types (with resolved styles), objects and relationships."""
    return {
        "objectTypes": [
            {
                "id": t.id,
                "key": t.key,
                "name": t.name,
                "attributes": _attribute_specs(t.attributes),
                "style": node_style(resolver.object_type(t.id)).to_dict(),
            }
            for t in dataset.object_types.values()
        ],
        "relationshipTypes": [
            {
                "id": t.id,
                "key": t.key,
                "name": t.name,
                "attributes": _attribute_specs(t.attributes),
                "rules": [_rule(rule) for rule in t.rules],
                "style": edge_style(resolver.relationship_type(t.id)).to_dict(),
            }
            for t in dataset.relationship_types.values()
        ],
        # Already in the dataset's stable (name, id) order; the runtime relies on it.
        "objects": [
            {
                "id": o.id,
                "typeId": o.type_id,
                "name": o.name,
                "sortKey": o.name.lower(),
                "foldKey": o.name.casefold(),
                "description": o.description,
                "attributes": o.attributes,
            }
            for o in dataset.objects.values()
        ],
        "relationships": [
            {
                "id": r.id,
                "typeId": r.type_id,
                "sourceId": r.source_id,
                "targetId": r.target_id,
                "attributes": r.attributes,
                "validFrom": r.valid_from,
                "validTo": r.valid_to,
            }
            for r in dataset.relationships.values()
        ],
    }


def build_bundle(model, dataset, config, *, publication: dict | None = None) -> dict:
    """
    Assemble the bundle for ``dataset`` (the *scoped, canonical* dataset).

    ``model`` supplies only the appearance and revision. ``publication`` is
    filled in once the record exists (id, sequence, publication date); a
    preview passes ``None``.
    """
    resolver = AppearanceService.resolver(model)
    theme = resolver.theme

    bundle = {
        "format": FORMAT,
        "formatVersion": Publication.FORMAT_VERSION,
        "sourceRevision": model.revision,
        "publication": {
            "title": config.title,
            "description": config.description,
            "revision": model.revision,
            **(publication or {}),
        },
        "presentation": {
            "themeColour": config.presentation.theme_colour,
            "canvasBackground": theme.canvas_background,
            "fontFamily": theme.font_family,
        },
        "defaultView": config.default_view.to_dict(),
        "graphTemplate": _graph_template(config.title, config.description, theme.canvas_background, dataset),
        "dataset": build_dataset_block(dataset, resolver),
        "facets": build_facets(dataset, resolver),
        "provenance": _provenance(model, dataset),
    }
    bundle["digest"] = compute_digest(bundle)
    return bundle


def with_publication(bundle: dict, publication: dict) -> dict:
    """The same bundle with the publication's own identity filled in (the digest is unaffected)."""
    return {**bundle, "publication": {**bundle["publication"], **publication}}
