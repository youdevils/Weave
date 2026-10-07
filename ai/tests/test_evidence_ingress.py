"""
Faithful carriage of AI evidence through the lifecycle (the live-run
investigation's failure classes), on synthetic fixtures:

- provenance: source_id is the logical source, segment_id the location --
  a segment named as a source is repaired, a mismatched pair rejected, for
  every producer;
- identity: OnyxJar owns flat global ids; identical duplicates collapse,
  conflicting ones are rejected precisely, re-declared known claims are
  references, repeated local ids across rounds never collide or nest, and no
  dependant is dropped without a logged reason;
- structural context is citable, never quotable;
- Gap Probe: per-requirement local evidence (with section retrieval and
  ancestors), row claims accepted, another row's claim rejected, an
  unsupported "found" recorded as such;
- pool-style distinctions are never bridged;
- blocked items report evidenced vs viable and their cascade root;
- trace capture + replay.
"""

import json
import tempfile
from types import SimpleNamespace

from django.test import override_settings

from model.models.proposal import ProposalChange

from ai.services.evidence_bundle import EvidenceBundle
from ai.services.evidence_graph import EvidenceGraph
from ai.services.orchestrator import run_ai_operation
from ai.services.reconcile.analysis import run_analysis
from ai.services.reconcile.compiler import compile_change_set
from ai.services.reconcile.near_miss import probe_payload
from ai.services.reconcile.state import ReconcileState
from ai.services.result_schema import OperationOutcome
from ai.services.semantic.index import SemanticModelIndex
from ai.services.stages.extraction import absorb
from ai.services.stages.gap_probe import incorporate
from ai.services.tracing import ReplayProvider, fate_table, load
from ai.tests.support import (
    AIServiceTestCase,
    ScriptedProvider,
    approve,
    assertion,
    entity,
    extraction,
    fact,
    frame,
    graph,
    probe,
    target,
    nothing_stated,
    verdict,
)

ORDERS = """# ACME LOGISTICS 2027

## Warehouses
- North Depot
- South Depot
- East Depot

## Orders
Customer | Order | Warehouse
Acme | O-1 | North Depot
Beta | O-2 | South Depot
"""

CUP = """# ACME CUP 2027

## Teams
- Red Lions
- Blue Owls

## Format
- Phase 1: two groups of two teams.

## Fixtures
Stage | Match | Ground
Group X | Red Lions v Blue Owls | Riverside
"""


class IngressTestCase(AIServiceTestCase):
    TEXT = ORDERS
    INTENT = "Add the warehouses listed in the document."

    def setUp(self):
        self.model = self.make_model(name="Logistics")
        self.warehouse = self.make_object_type(self.model, key="warehouse")
        self.order = self.make_object_type(self.model, key="order")
        self.served_from = self.make_relationship_type(self.model, key="served_from")
        self.make_rule(self.served_from, self.order, self.warehouse, object_minimum=1, subject_minimum=1)
        self.bundle = EvidenceBundle.from_assets([{"name": "doc.txt", "content": self.TEXT}])
        self.rs = ReconcileState(frame=frame([target("T1", "warehouses", "warehouses")]))
        self.run = SimpleNamespace(state=SimpleNamespace(reconcile=self.rs), bundle=self.bundle, intent=SimpleNamespace(text=self.INTENT))

    def seg(self, prefix):
        return next(s.segment_id for s in self.bundle.segments() if s.text.startswith(prefix))

    def absorb(self, *items, origin="extraction", replace_ids=()):
        return absorb(self.run, graph(*items), origin=origin, replace_ids=replace_ids)

    def fates(self, identifier):
        return [e["outcome"] for e in self.rs.ingress_log if e["id"] == identifier]

    def depot(self, eid="E1", name="North Depot"):
        return entity(eid, name, "warehouse", hint="warehouse", excerpt=name)

    def order_row(self, oid="E2", aid="A1", order="O-1", depot="E1", row="Acme | O-1 | North Depot", **kwargs):
        return [entity(oid, order, "order", hint="order", excerpt=order),
                assertion(aid, oid, "ships from", depot, hint="served_from", excerpt=row, **kwargs)]


class ProvenanceIngressTests(IngressTestCase):

    def test_a_segment_named_as_the_source_is_repaired(self):
        item = self.depot()
        item.provenance[0].source_id = self.seg("- North Depot")

        self.absorb(item)

        accepted = self.rs.graph.entity("E1")
        self.assertEqual((accepted.provenance[0].source_id, accepted.provenance[0].segment_id), ("S1", self.seg("- North Depot")))
        self.assertIn("repaired", self.fates("E1"))

    def test_a_segment_from_another_source_is_rejected(self):
        self.bundle = EvidenceBundle.from_assets([{"name": "a.txt", "content": self.TEXT}, {"name": "b.txt", "content": "North Depot is closed."}])
        self.run.bundle = self.bundle
        item = self.depot()
        item.provenance[0].source_id, item.provenance[0].segment_id = "S1", "S2#1"

        self.absorb(item)

        self.assertIsNone(self.rs.graph.entity("E1"))
        self.assertEqual(self.rs.pending_items["E1"][1][0].code, "source_segment_mismatch")

    def test_no_accepted_claim_ever_names_a_segment_as_its_source(self):
        items = [self.depot(), *self.order_row()]
        for item in items:
            item.provenance[0].source_id = self.bundle.segments_containing("S1", item.provenance[0].excerpt)[0].segment_id

        self.absorb(*items)

        sources = {p.source_id for i in self.rs.graph.items() for p in i.provenance}
        self.assertEqual(sources, {"S1"})
        self.assertEqual(len(self.rs.graph.items()), 3)


class IdentityIngressTests(IngressTestCase):

    def test_identical_duplicate_definitions_collapse(self):
        self.absorb(self.depot(), self.depot(), *self.order_row())

        self.assertEqual([e.eid for e in self.rs.graph.entities], ["E1", "E2"])
        self.assertIn("collapsed", self.fates("E1"))
        self.assertIsNotNone(self.rs.graph.assertion("A1"))

    def test_conflicting_duplicates_are_rejected_and_their_dependants_logged(self):
        self.absorb(self.depot(), self.depot(name="South Depot"), *self.order_row())

        self.assertIsNone(self.rs.graph.entity("E1"))
        self.assertIn("rejected", self.fates("E1"))
        self.assertIn("dropped_dependant", self.fates("A1"))  # never silent
        self.assertIn("E1", next(e["reason"] for e in self.rs.ingress_log if e["id"] == "A1"))

    def test_a_redeclared_known_claim_is_a_reference(self):
        self.absorb(self.depot())

        self.absorb(self.depot(), *self.order_row(), origin="probe")

        self.assertEqual(len(self.rs.graph.entities), 2)
        self.assertEqual(self.rs.graph.assertion("A1").object_eid, "E1")

    def test_reused_local_ids_across_rounds_never_collide_or_nest(self):
        for round_number, (order, depot, row) in enumerate((("O-1", "North Depot", "Acme | O-1 | North Depot"),
                                                            ("O-2", "South Depot", "Beta | O-2 | South Depot")), 1):
            self.absorb(self.depot(name=depot), *self.order_row(order=order, row=row), origin=f"probe")

        ids = [i.eid if hasattr(i, "eid") else i.aid for i in self.rs.graph.items()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(len(ids), 6)
        self.assertTrue(all("_" not in i and "#" not in i for i in ids), ids)
        for a in self.rs.graph.assertions:
            subject, obj = self.rs.graph.entity(a.subject_eid), self.rs.graph.entity(a.object_eid)
            self.assertIn(subject.name, a.provenance[0].excerpt)
            self.assertIn(obj.name, a.provenance[0].excerpt)

    def test_a_correction_replacement_keeps_its_id(self):
        bad = self.depot()
        bad.provenance[0].excerpt = "North Depott"
        self.absorb(bad)
        self.assertIn("E1", self.rs.pending_items)

        self.rs.pending_items.pop("E1")
        self.absorb(self.depot(), origin="extraction_correction", replace_ids={"E1"})

        self.assertIsNotNone(self.rs.graph.entity("E1"))


class StructuralContextTests(IngressTestCase):

    def test_payloads_carry_citable_ancestors_never_rendered_paths(self):
        row = self.bundle.segment(self.seg("Acme | O-1"))

        context = row.context()

        self.assertEqual(context["within"], row.ancestor_ids)
        self.assertNotIn(">", json.dumps(context))
        self.assertEqual(self.bundle.segment(row.ancestor_ids[-1]).text, "Customer | Order | Warehouse")

    def test_quoting_a_heading_path_is_reported_as_such(self):
        item = self.depot()
        item.provenance[0].excerpt = "ACME LOGISTICS 2027 > Warehouses"

        self.absorb(item)

        self.assertEqual(self.rs.pending_items["E1"][1][0].code, "context_not_quotable")

    def test_a_heading_plus_item_structural_claim_is_accepted(self):
        company = entity("E9", "Acme Logistics", "company", excerpt="ACME LOGISTICS 2027")
        claim = assertion("A9", "E9", "lists the warehouse", "E1", support="structural",
                          spans=[("ACME LOGISTICS 2027", "S1", self.seg("ACME")), ("North Depot", "S1", self.seg("- North Depot"))])

        self.absorb(company, self.depot(), claim)

        self.assertIsNotNone(self.rs.graph.assertion("A9"))


class RowProbeTests(IngressTestCase):

    def analysis(self):
        return run_analysis(self.rs, index=SemanticModelIndex.load(self.model), bundle=self.bundle)

    def test_a_probe_pack_holds_only_the_entitys_rows_and_their_context(self):
        self.absorb(self.depot())
        analysis = self.analysis()
        requirement = analysis.probe_requests[0]

        requirements, segments, coverage = probe_payload([requirement], analysis, index=SemanticModelIndex.load(self.model), bundle=self.bundle)

        texts = [s["text"] for s in segments]
        self.assertIn("Acme | O-1 | North Depot", texts)
        self.assertIn("Customer | Order | Warehouse", texts)
        self.assertNotIn("Beta | O-2 | South Depot", texts)
        self.assertEqual(coverage[requirement.requirement_id], "complete")

    def test_row_claims_are_kept_another_rows_claim_is_refused_and_an_unbacked_found_is_recorded(self):
        self.absorb(self.depot())
        analysis = self.analysis()
        self.rs.analysis = analysis
        requirement = analysis.probe_requests[0]
        self.rs.probe_payloads = {requirement.requirement_id: {"coverage": "complete", "_entity_ids": ["E1"]}}
        good = probe(*self.order_row(oid="X1", aid="X2"), verdicts=[verdict(requirement.requirement_id, "found", claim_ids=["X2"])])

        incorporate(self.run, good)

        self.assertEqual(self.rs.probe_outcomes[requirement.requirement_id], "found")
        self.assertEqual(self.rs.graph.assertion("X2").object_eid, "E1")

        # The same requirement answered from another depot's row: refused by
        # L2, and the "found" it claims is recorded as unsupported.
        self.rs.probed.clear()
        wrong = probe(*self.order_row(oid="Y1", aid="Y2", order="O-2", row="Beta | O-2 | South Depot"),
                      verdicts=[verdict(requirement.requirement_id, "found", claim_ids=["Y2"])])
        incorporate(self.run, wrong)

        self.assertIsNone(self.rs.graph.assertion("Y2"))
        self.assertEqual(self.rs.probe_outcomes[requirement.requirement_id], "found_unsupported")


class SectionRetrievalAndPoolTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model(name="Cup")
        types = {k: self.make_object_type(self.model, key=k) for k in ("tournament", "team", "stage", "match", "ground")}
        rel = {k: self.make_relationship_type(self.model, key=k) for k in ("has_team", "has_match", "plays_in", "played_at")}
        self.make_rule(rel["has_team"], types["tournament"], types["team"], object_minimum=2)
        self.make_rule(rel["has_match"], types["stage"], types["match"], object_minimum=1)
        self.make_rule(rel["played_at"], types["match"], types["ground"])
        self.bundle = EvidenceBundle.from_assets([{"name": "cup.txt", "content": CUP}])

    def seg(self, prefix):
        return next(s.segment_id for s in self.bundle.segments() if s.text.startswith(prefix))

    def analyse(self, *items, targets=(("T1", "stages", "stages"),)):
        rs = ReconcileState(frame=frame([target(*t) for t in targets]), graph=graph(*items))
        return run_analysis(rs, index=SemanticModelIndex.load(self.model), bundle=self.bundle)

    def test_a_section_under_a_heading_naming_the_entity_is_retrieved(self):
        analysis = self.analyse(entity("E1", "Acme Cup", "tournament", hint="tournament", excerpt="ACME CUP 2027"),
                                targets=(("T1", "tournament", "stages"),))
        requirement = next(r for r in analysis.probe_requests if analysis.cluster_name(r.cluster_id) == "Acme Cup")

        _, segments, _ = probe_payload([requirement], analysis, index=SemanticModelIndex.load(self.model), bundle=self.bundle)

        texts = [s["text"] for s in segments]
        self.assertIn("- Red Lions", texts)
        self.assertLess(texts.index("- Red Lions"), texts.index("Stage | Match | Ground") if "Stage | Match | Ground" in texts else 99)

    def test_a_group_named_in_a_stage_column_is_never_bridged_to_the_phase(self):
        analysis = self.analyse(
            entity("E1", "Phase 1", "stage", hint="stage", excerpt="Phase 1"),
            entity("E2", "Group X", "stage", hint="stage", excerpt="Group X"),
            entity("E3", "Red Lions v Blue Owls", "match", hint="match", excerpt="Red Lions v Blue Owls"),
            assertion("A1", "E2", "includes match", "E3", hint="has_match", excerpt="Group X | Red Lions v Blue Owls"),
        )

        self.assertEqual(len(analysis.clusters.clusters), 3)
        self.assertEqual(analysis.clusters.possible_same_as, [])
        self.assertEqual(analysis.scope.outcomes[next(c for c in analysis.clusters.clusters if analysis.cluster_name(c) == "Group X")], "selected")
        phase = next(c for c in analysis.clusters.clusters if analysis.cluster_name(c) == "Phase 1")
        self.assertIn(analysis.scope.outcomes[phase], ("blocked",))
        self.assertFalse([a for a, m in analysis.assertions.items() if phase in (m.subject_cid, m.object_cid)])


class CascadeTests(AIServiceTestCase):
    """Ground <- Fixture <- Round <- Competition: every ground needs a fixture,
    a fixture needs a round, a round needs its competition (structural)."""

    TEXT = "# RIVER LEAGUE 2027\n\n## Rounds\n- Round 1\n\n## Fixtures\nRound | Fixture | Ground\nRound 1 | Owls v Lions | Riverside\n"

    def setUp(self):
        self.model = self.make_model(name="League")
        t = {k: self.make_object_type(self.model, key=k) for k in ("competition", "round", "fixture", "ground")}
        r = {k: self.make_relationship_type(self.model, key=k) for k in ("has_round", "has_fixture", "played_at")}
        self.make_rule(r["has_round"], t["competition"], t["round"], object_minimum=1, subject_minimum=1)
        self.make_rule(r["has_fixture"], t["round"], t["fixture"], object_minimum=1, subject_minimum=1)
        self.make_rule(r["played_at"], t["fixture"], t["ground"], object_minimum=1, subject_minimum=1)
        self.bundle = EvidenceBundle.from_assets([{"name": "league.txt", "content": self.TEXT}])

    def seg(self, prefix):
        return next(s.segment_id for s in self.bundle.segments() if s.text.startswith(prefix))

    def items(self, *, with_root=True):
        row = "Round 1 | Owls v Lions | Riverside"
        items = [
            entity("C", "River League", "competition", hint="competition", excerpt="RIVER LEAGUE 2027"),
            entity("R", "Round 1", "round", hint="round", excerpt="Round 1"),
            entity("F", "Owls v Lions", "fixture", hint="fixture", excerpt="Owls v Lions"),
            entity("G", "Riverside", "ground", hint="ground", excerpt="Riverside"),
            assertion("A2", "R", "includes", "F", hint="has_fixture", excerpt=row),
            assertion("A3", "F", "is played at", "G", hint="played_at", excerpt=row),
        ]
        if with_root:
            items.append(assertion("A1", "C", "has round", "R", hint="has_round", support="structural",
                                   spans=[("RIVER LEAGUE 2027", "S1", self.seg("RIVER")), ("Round 1", "S1", self.seg("- Round 1"))]))
        return items

    def analyse(self, items):
        rs = ReconcileState(frame=frame([target("T1", "grounds", "grounds")]), graph=graph(*items))
        return run_analysis(rs, index=SemanticModelIndex.load(self.model), bundle=self.bundle)

    def test_a_valid_structural_root_lets_the_whole_chain_compile(self):
        analysis = self.analyse(self.items())

        change_set, _ = compile_change_set(analysis, index=SemanticModelIndex.load(self.model))
        self.assertEqual(sorted(a.name for a in change_set.actions if a.kind == "create_object"),
                         ["Owls v Lions", "River League", "Riverside", "Round 1"])

    def test_breaking_only_the_root_reports_evidence_and_the_cascade(self):
        analysis = self.analyse(self.items(with_root=False))

        blocked = analysis.blocked_targets(SemanticModelIndex.load(self.model), {})
        ground = next(b for b in blocked if b["target"] == "Riverside")
        own = ground["missing_requirements"][0]
        # The evidence names the fixture; it just can't be added.
        self.assertEqual((own["evidenced"], own["viable"]), (1, 0))
        self.assertEqual(ground["cascade"]["chain"], ["Riverside", "Owls v Lions", "Round 1"])
        self.assertEqual(ground["cascade"]["cause"]["relationship_type_key"], "has_round")


class EveryIngressRejectsUnanchoredClaimsTests(IngressTestCase):

    def test_extraction_probe_and_verifier_all_refuse_an_unanchored_canonical_claim(self):
        canonical = assertion("A7", "E1", "served_from", "E3", hint="served_from", excerpt="North Depot")
        for origin in ("extraction", "probe"):
            with self.subTest(origin=origin):
                self.rs = ReconcileState(frame=self.rs.frame)
                self.run.state.reconcile = self.rs
                self.absorb(self.depot(), entity("E3", "O-1", "order", excerpt="O-1"), canonical, origin=origin)
                self.assertIsNone(self.rs.graph.assertion("A7"))
                self.assertEqual(self.rs.pending_items["A7"][1][0].code, "unanchored_claim")


class TraceReplayTests(IngressTestCase):

    def test_a_traced_run_replays_to_the_same_outcome_with_a_fate_table(self):
        frame_ = frame([target("T1", "warehouses", "warehouses")])
        depot = self.depot()
        depot.provenance[0].segment_id = self.seg("- North Depot")
        # South Depot's row (a warehouse nobody extracted) is re-asked, then
        # probed as the warehouses target's gap.
        script = [extraction(frame_, depot, *self.order_row()), extraction(frame()), nothing_stated, approve()]
        assets = [{"name": "doc.txt", "content": self.TEXT}]
        with tempfile.TemporaryDirectory() as directory, override_settings(AI_TRACE_DIR=directory):
            first = run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=self.INTENT,
                                     assets=assets, provider=ScriptedProvider(script))
            path = f"{directory}/{first.execution_id}"
            steps = load(path)
            ProposalChange.objects.all().delete()
            from model.models.proposal import Proposal

            Proposal.objects.all().delete()
            replayed = run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=self.INTENT,
                                        assets=assets, provider=ReplayProvider(path))

        self.assertEqual((first.outcome, replayed.outcome), (OperationOutcome.READY_FOR_REVIEW, OperationOutcome.READY_FOR_REVIEW))
        self.assertEqual([s["stage"] for s in steps if s["kind"] == "provider"],
                         ["extraction", "extraction_correction", "gap_probe", "verification"])
        snapshot = next(s["snapshot"] for s in reversed(steps) if s["kind"] == "deterministic")
        fates = {row["id"]: row for row in fate_table(snapshot)}
        self.assertEqual((fates["A1"]["ingress"], fates["A1"]["ground"], fates["A1"]["mapping"]), ("accepted", "anchored", "mapped"))
