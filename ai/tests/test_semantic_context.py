"""
The canonical semantic representation (ai.services.semantic) and its
boundaries:

- canonical UUIDs and viewer/projection identifiers never appear in
  OnyxJar-generated semantic AI structures -- checked on the structures'
  own identifier fields and schemas, never by scanning free text (user
  intent/evidence may legitimately contain UUID-looking text and is passed
  through verbatim);
- inactive entities are visible (with their lifecycle state);
- Create's planning context is bounded, naming every truncated type.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType

from ai.services.semantic import catalogue as catalogue_module
from ai.services.semantic.catalogue import OntologyCatalogue, build_catalogue
from ai.services.semantic.index import SemanticModelIndex
from ai.services.semantic.records import ObjectRecord, RelationshipRecord
from ai.services.semantic.selection import SemanticContext, select_full_context
from ai.services.staging import DeltaEntry, ProjectedDelta
from ai.tests.rugby import RugbyFixture

BANNED_FIELD_NAMES = {
    "id", "typeId", "relationshipId", "relationship_type_id", "inView", "hiddenConnectionIds",
    "display", "connectionCount", "isProposed", "isCreated", "model_id",
}


def _field_names(model_cls, seen=None):
    """Every field name declared anywhere in a Pydantic model's schema tree."""

    seen = seen if seen is not None else set()
    names = set()
    if model_cls in seen:
        return names
    seen.add(model_cls)
    for name, info in model_cls.model_fields.items():
        names.add(name)
        for candidate in _nested_models(info.annotation):
            names |= _field_names(candidate, seen)
    return names


def _nested_models(annotation):
    from pydantic import BaseModel

    found = []
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        found.append(annotation)
    for arg in getattr(annotation, "__args__", ()) or ():
        found.extend(_nested_models(arg))
    return found


class SemanticSchemaTests(SimpleTestCase):

    def test_semantic_structures_declare_no_persistence_or_viewer_identifiers(self):
        for model_cls in (OntologyCatalogue, ObjectRecord, RelationshipRecord, SemanticContext, ProjectedDelta, DeltaEntry):
            with self.subTest(model=model_cls.__name__):
                self.assertFalse(_field_names(model_cls) & BANNED_FIELD_NAMES, _field_names(model_cls) & BANNED_FIELD_NAMES)

    def test_ai_facing_modules_do_not_import_viewer_projection_code(self):
        banned = (
            "model.services.model_graph.details",
            "model.services.model_graph.projection",
            "model.services.model_graph.query",
            "model.services.ontology_graph",
        )
        root = Path(catalogue_module.__file__).resolve().parents[1]
        files = [*root.joinpath("semantic").glob("*.py"), *root.joinpath("stages").glob("*.py"), *root.joinpath("workflow").glob("*.py"),
                 *root.joinpath("reconcile").glob("*.py"), root / "resolution.py", root / "staging.py", root / "change_set.py",
                 root / "artifacts.py", root / "evidence_graph.py", root / "intent_frame.py", root / "provenance.py",
                 root / "grounding.py", root / "sources.py", root / "evidence_bundle.py"]
        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imported = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]
            imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
            for module in imported:
                with self.subTest(file=path.name, module=module):
                    self.assertFalse(module.startswith(banned))


class SemanticIndexTests(RugbyFixture):

    def canonical_ids(self):
        ids = set()
        for model_cls in (ObjectType, RelationshipType, Object, Relationship):
            ids |= {str(pk) for pk in model_cls.objects.filter(model=self.model).values_list("id", flat=True)}
        ids.add(str(self.model.id))
        return ids

    def test_inactive_entities_are_visible_with_their_lifecycle_state(self):
        retired = self.make_object(self.model, self.venue_type, name="Old Ground", key="old_ground", is_active=False)
        self.venue_type.is_active = False
        self.venue_type.save()

        index = SemanticModelIndex.load(self.model)
        catalogue = build_catalogue(index)

        self.assertFalse(index.objects[str(retired.id)].is_active)
        venue = next(t for t in catalogue.object_types if t.key == "venue")
        self.assertFalse(venue.active)

    def test_identifier_fields_hold_semantic_keys_never_canonical_ids(self):
        index = SemanticModelIndex.load(self.model)
        context = select_full_context(index)
        canonical = self.canonical_ids()

        identifier_values = []
        for object_type in context.catalogue.object_types:
            identifier_values += [object_type.key, *(a.key for a in object_type.attributes)]
        for relationship_type in context.catalogue.relationship_types:
            identifier_values.append(relationship_type.key)
            for rule in relationship_type.rules:
                identifier_values += [rule.subject_type_key, rule.object_type_key]
        for record in context.objects:
            identifier_values += [record.type_key, record.key]
        for record in context.relationships:
            identifier_values += [record.relationship_type_key, record.subject.type_key, record.subject.key,
                                  record.object.type_key, record.object.key]

        self.assertTrue(identifier_values)
        self.assertFalse(set(identifier_values) & canonical)
        self.assertIn("championship_2027", identifier_values)
        self.assertIn("has_team", identifier_values)

    def test_semantic_ref_translates_canonical_ids_to_keys(self):
        index = SemanticModelIndex.load(self.model)

        self.assertEqual(index.semantic_ref("Object", self.tournament.id)["key"], "championship_2027")
        self.assertEqual(index.semantic_ref("RelationshipType", self.has_team.id), {"entity": "relationship_type", "key": "has_team"})

    def test_match_hints_by_key_name_and_alias(self):
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park")
        index = SemanticModelIndex.load(self.model)

        by_name = index.match_objects(self.venue_type.id, "EDEN park")
        by_alias = index.match_objects(self.venue_type.id, "The Garden of Eden", aliases=["Eden Park"])

        self.assertEqual([m.object.key for m in by_name], ["eden_park"])
        self.assertEqual([m.match for m in by_alias], ["key"])


class SelectionTests(RugbyFixture):

    def test_large_models_are_trimmed_and_the_trimmed_types_named(self):
        from django.test import override_settings

        for number in range(5):
            self.make_object(self.model, self.venue_type, name=f"Ground {number}", key=f"ground_{number}")
        index = SemanticModelIndex.load(self.model)

        with override_settings(AI_CONTEXT_MAX_OBJECTS=8):
            context = select_full_context(index)

        self.assertLessEqual(len(context.objects), 8)
        self.assertIn("venue", context.truncated_types)
