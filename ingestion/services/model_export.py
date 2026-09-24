"""
Model Export: the complete canonical model as one portable JSON document.

Deliberately all-or-nothing (no filters, no object selection): the model's
ontology (object/relationship types, their attributes and cardinality rules)
and its canonical data (objects and relationships), reusing the same
``EffectiveDataset`` Publication already builds from, so the shape here is not
a second, hand-rolled representation of the model.

Never writes canonical data; read-only.
"""

from __future__ import annotations

from django.utils.text import slugify

from model.services.model_graph.loader import load_effective_dataset

FORMAT = "onyxjar"
VERSION = 1


def _attribute_specs(specs) -> list[dict]:
    return [
        {"key": s.key, "name": s.name, "dataType": s.data_type, "choices": list(s.choices)} for s in specs
    ]


def _rule(rule) -> dict:
    return {
        "subjectTypeId": rule.subject_type_id,
        "objectTypeId": rule.object_type_id,
        "subjectMinimum": rule.subject_minimum,
        "subjectMaximum": rule.subject_maximum,
        "objectMinimum": rule.object_minimum,
        "objectMaximum": rule.object_maximum,
    }


def build_export(model) -> dict:
    """The full canonical model (ontology + data) as a plain, JSON-serialisable dict."""

    dataset = load_effective_dataset(model, proposal=None)

    return {
        "format": FORMAT,
        "version": VERSION,
        "model": {
            "name": model.name,
            "description": model.description,
            "purpose": model.purpose,
            "scope": model.scope,
            "exclusions": model.exclusions,
        },
        "objectTypes": [
            {
                "id": t.id,
                "key": t.key,
                "name": t.name,
                "attributes": _attribute_specs(t.attributes),
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
            }
            for t in dataset.relationship_types.values()
        ],
        "objects": [
            {
                "id": o.id,
                "typeId": o.type_id,
                "name": o.name,
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


def export_filename(model) -> str:
    """``<model-slug>-r<revision>.json``, safe for ``Content-Disposition``."""

    suffix = f"-r{model.revision}.json"
    slug = slugify(model.name or "")[: 120 - len(suffix)].strip("-") or "model"
    return f"{slug}{suffix}"
