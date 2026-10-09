"""
Correction-stage relationship anchors (ai/README.md): when a rejected
assertion fails grounding, the correction payload surfaces where its
claimed subject and object could actually be related -- a locator for the
model, never a claim, and never more permissive than the validator it
serves.

    direct       one segment states both sides -- cite it
    structural   an ancestor/descendant pair, one naming each side (nested
                 headings included, not flattened)
    neither      no eligible direct or structural anchor was found for this
                 specific pair -- a hint to withdraw, not proof the
                 relationship doesn't exist

The central contradiction this fixes: a probe/extraction claim can name an
entity (accepted) while the relationship about it is rejected for citing the
wrong segment -- a human reading the output sees "the probe found it"; the
relational row stays `uncovered` regardless, because a row's coverage needs
an accepted assertion or fact, never an entity alone.
"""

from __future__ import annotations

import types

from django.test import override_settings

from ai.services.evidence_bundle import EvidenceBundle
from ai.services.evidence_graph import EvidenceGraph
from ai.services.grounding import grounding_issues, relationship_anchors
from ai.services.reconcile.analysis import run_analysis
from ai.services.reconcile.coverage import CLAIMED, UNCOVERED, compute_coverage
from ai.services.reconcile.ingress import ingest
from ai.services.reconcile.mapping import _similar_types
from ai.services.reconcile.state import ReconcileState
from ai.services.reconcile import questions as q
from ai.services.semantic.index import SemanticModelIndex
from ai.services.stages.extraction import correction_anchors, segment_payload
from ai.services.stages.gap_probe import _supports
from ai.tests.support import AIServiceTestCase, assertion, entity, frame, graph, target

TEXT = """PACIFIC TEST CHAMPIONSHIP 2027

Venues
Venue | City
FMG Stadium Waikato | Hamilton

Teams
Team | Country
South Africa | Africa
Tonga | Oceania

Example fixtures
Stage | Match | Venue
Pool A | New Zealand v Fiji | Eden Park
Pool B | South Africa v Tonga | FMG Stadium Waikato
"""

VENUE_ROW = "S1#t1.r1"          # FMG Stadium Waikato | Hamilton
TEAM_ROW = "S1#t2.r1"           # South Africa | Africa
OTHER_MATCH_ROW = "S1#t3.r1"    # Pool A | New Zealand v Fiji | Eden Park
FIXTURE_ROW = "S1#t3.r2"        # Pool B | South Africa v Tonga | FMG Stadium Waikato
TITLE = "S1#1"


def bundle():
    return EvidenceBundle.from_assets([{"name": "flyer.txt", "content": TEXT}])


class RelationshipAnchorsUnitTests(AIServiceTestCase):

    def test_a_single_segment_stating_both_sides_is_direct(self):
        anchors = relationship_anchors(["South Africa v Tonga"], ["FMG Stadium Waikato"], bundle())

        self.assertEqual(anchors, {"direct": [FIXTURE_ROW], "structural": []})

    def test_nested_headings_give_a_structural_pair_not_the_nearer_heading(self):
        anchors = relationship_anchors(["PACIFIC TEST CHAMPIONSHIP 2027"], ["South Africa"], bundle())

        # The title heading (the subject's own name) paired with the team row --
        # never the nearer "Teams" heading, which doesn't name the subject.
        self.assertIn((TITLE, TEAM_ROW), anchors["structural"])
        self.assertEqual(anchors["direct"], [])

    def test_no_eligible_anchor_for_a_pair_nothing_connects(self):
        """FMG Stadium Waikato and New Zealand v Fiji are each mentioned, but
        never together, and never structurally related (siblings under the
        title, not ancestor/descendant) -- the A1009 wrong-entity case."""

        anchors = relationship_anchors(["FMG Stadium Waikato"], ["New Zealand v Fiji"], bundle())

        self.assertEqual((anchors["direct"], anchors["structural"]), ([], []))
        self.assertEqual(set(anchors["subject_only"]), {VENUE_ROW, FIXTURE_ROW})
        self.assertEqual(anchors["object_only"], [OTHER_MATCH_ROW])

    def test_the_helper_never_implies_evidence_the_validator_would_reject(self):
        """Locator only: the same wrong pairing is still rejected by grounding,
        regardless of what relationship_anchors offers."""

        wrong = assertion("A1", "E1", "is played at", "E2", hint="played_at", excerpt="FMG Stadium Waikato")
        wrong.provenance[0].segment_id = VENUE_ROW
        patch = graph(
            entity("E1", "New Zealand v Fiji", "match", hint="match", excerpt="New Zealand v Fiji"),
            entity("E2", "FMG Stadium Waikato", "venue", hint="venue", excerpt="FMG Stadium Waikato"),
            wrong,
        )
        patch.entities[0].provenance[0].segment_id = OTHER_MATCH_ROW
        patch.entities[1].provenance[0].segment_id = VENUE_ROW

        issues = grounding_issues(patch, bundle=bundle())

        self.assertEqual([i.code for i in issues if i.item_id == "A1"], ["unanchored_claim"])


# The fake run has no execution to trace to: tracing must be off however the
# environment running the suite is configured (the dev container sets it).
@override_settings(AI_TRACE_DIR=None)
class CorrectionAnchorsPayloadTests(AIServiceTestCase):
    """`correction_anchors` (ai.services.stages.extraction), shared by both
    correction stages: the exact entry a correction payload gets."""

    def fake_run(self, rs):
        return types.SimpleNamespace(state=types.SimpleNamespace(reconcile=rs), bundle=bundle())

    def test_none_when_the_issue_is_not_unanchored_claim(self):
        rs = ReconcileState(graph=graph(entity("E1", "FMG Stadium Waikato", "venue", excerpt="FMG Stadium Waikato")))
        item = assertion("A1", "E1", "is played at", "E2", hint="played_at", excerpt="x")

        from ai.services.feedback import issue

        self.assertIsNone(correction_anchors(self.fake_run(rs), item, [issue("excerpt_not_found", "x", item_id="A1")], stage="extraction_correction"))

    def test_anchors_for_a_rejected_structural_claim_preserve_ancestry(self):
        rs = ReconcileState(graph=graph(
            entity("E1", "PACIFIC TEST CHAMPIONSHIP 2027", "tournament", excerpt="PACIFIC TEST CHAMPIONSHIP 2027"),
            entity("E2", "South Africa", "team", excerpt="South Africa"),
        ))
        item = assertion("A1", "E1", "has team", "E2", hint="has_team_2", support="structural", excerpt="Teams")

        from ai.services.feedback import issue

        found = correction_anchors(self.fake_run(rs), item, [issue("unanchored_claim", "x", item_id="A1")], stage="extraction_correction")

        self.assertEqual(found["direct"], [])
        # The requested pair is present, and so is the containment it sits in
        # (the "Teams" heading, the table) -- ancestry preserved, not flattened.
        pair_ids = [{s["segment_id"] for s in pair} for pair in found["structural"]]
        self.assertTrue(any({TITLE, TEAM_ROW} <= ids for ids in pair_ids))
        # The row is shown with its own `within` chain, not a bare id.
        row = next(s for pair in found["structural"] for s in pair if s["segment_id"] == TEAM_ROW)
        self.assertIn(TITLE, row["within"])


class FullLifecycleTests(AIServiceTestCase):
    """The central contradiction, reproduced and then closed end to end."""

    def setUp(self):
        self.model = self.make_model(name="Fixtures")
        self.venue = self.make_object_type(self.model, key="venue")
        self.match = self.make_object_type(self.model, key="match")
        self.team = self.make_object_type(self.model, key="team")
        self.played_at = self.make_relationship_type(self.model, key="played_at")
        self.has_team = self.make_relationship_type(self.model, key="has_team")
        self.make_rule(self.played_at, self.match, self.venue, object_minimum=1, subject_minimum=1, subject_maximum=1)
        self.make_rule(self.has_team, self.match, self.team, object_minimum=2)
        self.bundle = bundle()
        self.index = SemanticModelIndex.load(self.model)

    def known_venue(self):
        venue = entity("E1", "FMG Stadium Waikato", "venue", hint="venue", excerpt="FMG Stadium Waikato")
        venue.provenance[0].segment_id = VENUE_ROW
        return venue

    def analyse(self, rs):
        return run_analysis(rs, index=self.index, bundle=self.bundle)

    def test_a_wrongly_anchored_relationship_leaves_the_row_uncovered(self):
        rs = ReconcileState(graph=graph(self.known_venue()), frame=frame([target("T1", "venues", "venues", hint="venue")]))

        match = entity("X1", "South Africa v Tonga", "match", hint="match", excerpt="South Africa v Tonga")
        match.provenance[0].segment_id = FIXTURE_ROW
        wrong = assertion("X2", "X1", "is played at", "E1", hint="played_at", excerpt="FMG Stadium Waikato")
        wrong.provenance[0].segment_id = VENUE_ROW  # the venue's own row -- never states the match
        patch = graph(match, wrong)

        ingested, mapping, ingress_issues = ingest(patch, rs=rs, bundle=self.bundle, origin="probe")
        issues = list(ingress_issues) + grounding_issues(ingested, bundle=self.bundle, known=rs.graph)
        rejected = {i.item_id for i in issues}

        self.assertEqual(rejected, {mapping["X2"]})
        accepted = ingested.without(rejected)
        self.assertEqual([e.eid for e in accepted.entities], [mapping["X1"]])
        self.assertEqual(accepted.assertions, [])
        rs.graph = rs.graph.appended(accepted)

        coverage = compute_coverage(self.bundle, rs.graph, rs.frame, self.index, {})
        self.assertEqual(coverage[FIXTURE_ROW].status, UNCOVERED)
        self.assertEqual(coverage[FIXTURE_ROW].cited_by, [])

        # Correction now has a real anchor: the fixture row states both sides.
        anchors = relationship_anchors(["South Africa v Tonga"], ["FMG Stadium Waikato"], self.bundle)
        self.assertEqual(anchors["direct"], [FIXTURE_ROW])

        # A corrected claim citing it is accepted, and the row becomes claimed.
        fixed = assertion("X2", "X1", "is played at", "E1", hint="played_at", excerpt="South Africa v Tonga | FMG Stadium Waikato")
        fixed.provenance[0].segment_id = FIXTURE_ROW
        ingested2, _, ingress_issues2 = ingest(graph(fixed), rs=rs, bundle=self.bundle, origin="probe", replace_ids={"X2"})
        issues2 = list(ingress_issues2) + grounding_issues(ingested2, bundle=self.bundle, known=rs.graph)
        self.assertEqual(issues2, [])
        rs.graph = rs.graph.appended(ingested2)

        coverage2 = compute_coverage(self.bundle, rs.graph, rs.frame, self.index, {})
        self.assertEqual(coverage2[FIXTURE_ROW].status, CLAIMED)
        self.assertEqual(coverage2[FIXTURE_ROW].cited_by, ["X2"])

        # Downstream consequence: the match is now reachable, and its own
        # has_team requirement (minimum 2, zero candidates) is a real gap.
        analysis = self.analyse(rs)
        match_cid = analysis.clusters.by_eid["X1"]
        self.assertIn(match_cid, analysis.scope.tentative)
        has_team_ids = [r.requirement_id for r in analysis.scope.unsatisfied if r.cluster_id == match_cid]
        self.assertTrue(has_team_ids)
        self.assertTrue(set(has_team_ids) <= {r.requirement_id for r in analysis.probe_requests})


class SupportsSafetyTests(AIServiceTestCase):
    """A probe verdict naming a claim_id that doesn't exist is never a crash
    and never a false 'found' -- ai.services.stages.gap_probe._supports."""

    def test_an_unknown_claim_id_is_never_supported(self):
        rs = ReconcileState(graph=EvidenceGraph())

        self.assertFalse(_supports(rs, {"_entity_ids": ["E1"]}, ["ghost-claim-id"]))
        self.assertFalse(_supports(rs, {"_target": "T1"}, ["ghost-claim-id"]))


class TypeFallbackSafetyTests(AIServiceTestCase):
    """OnyxJar's own type-mapping fallback never invents a kind merely
    because the catalogue happens to have one with a similar name."""

    def test_similar_types_shares_no_words_with_an_unrelated_label(self):
        model = self.make_model(name="Catalogue")
        self.make_object_type(model, key="stage", name="Stage")
        index = SemanticModelIndex.load(model)

        found = _similar_types(index, ["pool", "group"])

        self.assertEqual(found, [])


class NoAnchorUnitTests(CorrectionAnchorsPayloadTests):
    """`no_anchor` (ai.services.stages.extraction): only an assertion whose
    sole defect is unanchored_claim, between two known entities no segment
    relates, skips its correction."""

    def state(self):
        return ReconcileState(graph=graph(
            entity("E1", "FMG Stadium Waikato", "venue", excerpt="FMG Stadium Waikato"),
            entity("E2", "New Zealand v Fiji", "match", excerpt="New Zealand v Fiji"),
            entity("E3", "South Africa v Tonga", "match", excerpt="South Africa v Tonga"),
        ))

    def check(self, item, *codes):
        from ai.services.feedback import issue
        from ai.services.stages.extraction import no_anchor

        return no_anchor(self.fake_run(self.state()), item, [issue(code, "x", item_id=item_id_of(item)) for code in codes])

    def test_a_pair_nothing_connects_is_not_re_asked(self):
        self.assertTrue(self.check(assertion("A1", "E1", "hosts", "E2", excerpt="FMG Stadium Waikato"), "unanchored_claim"))

    def test_a_pair_a_segment_connects_is_re_asked(self):
        self.assertFalse(self.check(assertion("A1", "E1", "hosts", "E3", excerpt="FMG Stadium Waikato"), "unanchored_claim"))

    def test_any_other_defect_keeps_the_re_ask(self):
        item = assertion("A1", "E1", "hosts", "E2", excerpt="FMG Stadium Waikato")

        self.assertFalse(self.check(item, "unanchored_claim", "self_reference"))
        self.assertFalse(self.check(item, "excerpt_not_in_segment"))

    def test_an_unknown_endpoint_keeps_the_re_ask(self):
        self.assertFalse(self.check(assertion("A1", "E1", "hosts", "E99", excerpt="FMG Stadium Waikato"), "unanchored_claim"))

    def test_only_assertions_qualify(self):
        self.assertFalse(self.check(entity("E9", "Nowhere", "venue", excerpt="Nowhere"), "unanchored_claim"))


def item_id_of(item):
    return getattr(item, "aid", None) or getattr(item, "eid", None)
