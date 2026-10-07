"""
I1 -- the EvidenceGraph records extracted evidence and is never required to
be ontology-valid: untyped entities, generic mentions, non-catalogue
predicates and ontology-impossible hints all validate clean; only structure
and provenance are checked, by a validator that cannot see the ontology.
"""

import ast
import inspect
from pathlib import Path

from django.test import SimpleTestCase

from ai.services import evidence_graph as evidence_graph_module
from ai.services.evidence_bundle import EvidenceBundle
from ai.services.evidence_graph import validate_evidence_graph
from ai.services.intent_frame import amend, FrameAmendment, validate_intent_frame
from ai.tests.rugby import FLYER_ASSETS, INTENT
from ai.tests.support import anchor, assertion, entity, fact, frame, graph, target


class EvidenceInvariantTests(SimpleTestCase):

    def setUp(self):
        self.bundle = EvidenceBundle.from_assets(FLYER_ASSETS)

    def validate(self, evidence, **kwargs):
        return validate_evidence_graph(evidence, bundle=self.bundle, intent_text=INTENT, **kwargs)

    def test_ontology_free_evidence_validates_clean(self):
        evidence = graph(
            entity("E1", "Forsyth Barr Stadium", "stadium", hint="no_such_type", excerpt="Forsyth Barr Stadium"),
            entity("E2", "Pool matches", "fixture", specificity="generic", excerpt="Pool matches"),
            entity("E3", "Pool Stage", "phase of competition"),
            assertion("A1", "E1", "hosts the pool fixtures of", "E3", hint="played_at", excerpt="Forsyth Barr Stadium | Dunedin | Pool matches"),
            assertion("A2", "E1", "is home of", "E2", excerpt="Pool matches"),
            fact("F1", "E1", "City", "Dunedin", excerpt="Dunedin"),
        )

        self.assertEqual(self.validate(evidence), [])

    def test_the_validator_cannot_see_the_ontology(self):
        parameters = set(inspect.signature(validate_evidence_graph).parameters)

        self.assertFalse(parameters & {"index", "catalogue", "model"})

    def test_evidence_and_grounding_modules_never_import_the_ontology(self):
        root = Path(evidence_graph_module.__file__).resolve().parent
        for name in ("evidence_graph.py", "grounding.py", "sources.py", "provenance.py", "evidence_bundle.py"):
            tree = ast.parse((root / name).read_text(encoding="utf-8"))
            imported = [node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module]
            imported += [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names]
            with self.subTest(module=name):
                self.assertFalse([m for m in imported if m.startswith(("ai.services.semantic", "ai.services.reconcile", "model."))])

    def test_structure_and_provenance_are_still_checked(self):
        evidence = graph(
            entity("E1", "Eden Park", "venue", excerpt="Eden Park"),
            entity("E1", "Eden Park again", "venue", excerpt="Eden Park"),
            assertion("A1", "E1", "played at", "E9", excerpt="played at Eden Park"),
            fact("F1", "E1", "Capacity", "60000", excerpt="Eden Park capacity: 60000"),
        )

        found = {(i.code, i.item_id) for i in self.validate(evidence)}
        self.assertIn(("duplicate_id", "E1"), found)
        self.assertIn(("dangling_reference", "A1"), found)
        self.assertIn(("excerpt_not_found", "F1"), found)


class IntentFrameTests(SimpleTestCase):

    def test_every_element_must_quote_the_intent(self):
        bad = frame([target("T1", "venues", "all the venues in Europe")], [anchor("N1", "2027 Championship", "the 2027 Championship")],
                    include_related=True, include_related_excerpt="every relationship")

        found = {(i.code, i.item_id) for i in validate_intent_frame(bad, INTENT)}
        self.assertEqual(found, {("excerpt_not_found", "T1"), ("excerpt_not_found", "include_related")})

    def test_amendments_add_and_remove_targets(self):
        original = frame([target("T1", "venues", "venues")])

        amended = amend(original, FrameAmendment(add_targets=[target("T2", "stages", "stages")], remove_target_ids=["T1"]))

        self.assertEqual([t.target_id for t in amended.targets], ["T2"])
        self.assertEqual(validate_intent_frame(amended, INTENT), [])
