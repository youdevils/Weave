"""
The evidence lifecycle corrections (ai/README.md, P1-P4), as classes of
failure rather than rugby strings:

- L2 grounding: claims whose cited evidence doesn't mention what they are
  about are refused (the "Pool Stage has match Eden Park" class); structural
  support needs a structural citation; intent + source structural support;
- coverage: claimed / dismissed / uncovered are distinct; a relational table
  row is only accounted for by an assertion or fact; dismissals are coverage
  decisions, never claims;
- homonyms: one label, two kinds -> two entities, no question;
- lexical mapping needs the predicate's words in the evidence;
- cardinality beyond a maximum: simultaneous -> constraint_conflict (never
  picked, never probed); time-separated -> "which is current";
- Gap Probe retrieval: local packs from anchored segments, no ontology keys;
- the international flyer end to end: tables extracted through the
  coverage gate, cascading requirements met, a partial result with honest
  blocks, and zero-result runs reviewed with full objection routing.
"""

import os
import unittest
from pathlib import Path

from django.conf import settings
from django.test import override_settings

from model.models.proposal import ProposalChange

from assisted.services.evidence_extraction import extract_text

from ai.services.evidence_bundle import EvidenceBundle
from ai.services.grounding import ANCHORED, STRUCTURAL, UNANCHORED, ground_graph
from ai.services.orchestrator import run_ai_operation
from ai.services.reconcile import questions as q
from ai.services.reconcile.analysis import run_analysis
from ai.services.reconcile.compiler import compile_change_set
from ai.services.reconcile.coverage import CLAIMED, DISMISSED, UNCOVERED, compute_coverage
from ai.services.reconcile.near_miss import probe_payload
from ai.services.reconcile.state import ReconcileState
from ai.services.reconcile.trace_policy import check_trace
from ai.services.result_schema import OperationOutcome
from ai.services.semantic.index import SemanticModelIndex
from ai.services.stages.extraction import plan_batches
from ai.tests.rugby import FLYER_ASSETS, RugbyFixture
from ai.tests.support import (
    AIServiceTestCase,
    ScriptedProvider,
    answers,
    approve,
    assertion,
    entity,
    extraction,
    fact,
    frame,
    graph,
    objection,
    probe,
    reject,
    target,
    verdict,
)

INTERNATIONAL_PDF = (Path(__file__).parent / "fixtures" / "international_rugby_flyer.pdf").read_bytes()


def flyer_assets():
    extracted = extract_text(INTERNATIONAL_PDF, filename="international_rugby_tournament_flyer.pdf")
    return [{"name": "international_rugby_tournament_flyer.pdf", "content": extracted.text, "blocks": extracted.blocks,
             "mime_type": extracted.mime_type}]


class GroundingTests(RugbyFixture):

    def setUp(self):
        super().setUp()
        self.bundle = EvidenceBundle.from_assets(FLYER_ASSETS)

    def ground(self, *items):
        from ai.services.evidence_graph import resolve_graph_segments

        return ground_graph(resolve_graph_segments(graph(*items), self.bundle), bundle=self.bundle)

    def test_a_relationship_its_evidence_never_mentions_is_unanchored(self):
        outcomes = self.ground(
            entity("E2", "Pool Stage", "stage"),
            entity("E6", "Eden Park", "venue", excerpt="Eden Park | Auckland"),
            assertion("A6", "E2", "has match", "E6", excerpt="Eden Park | Auckland | Opening match and final"),
        )

        self.assertEqual(outcomes["A6"], UNANCHORED)

    def test_a_segment_stating_both_endpoints_anchors_it(self):
        outcomes = self.ground(
            entity("E3", "Match 1", "match", excerpt="Match 1: New Zealand v Fiji"),
            entity("E6", "Eden Park", "venue", excerpt="Eden Park | Auckland"),
            # The excerpt alone lacks "Match 1"; its segment states both.
            assertion("A5", "E3", "played at", "E6", excerpt="played at Eden Park"),
        )

        self.assertEqual(outcomes["A5"], ANCHORED)

    def test_structural_support_needs_a_structural_citation(self):
        championship = entity("E1", "2027 Championship", "championship", excerpt="2027 CHAMPIONSHIP")
        stage = entity("E2", "Pool Stage", "stage")
        explicit = assertion("A1", "E1", "lists", "E2", spans=[("2027 CHAMPIONSHIP", "S1"), ("Pool Stage", "S1")])
        structural = explicit.model_copy(update={"aid": "A2", "support": "structural"})
        unrelated = assertion("A3", "E1", "lists", "E2", support="structural", spans=[("Eden Park capacity", "S1"), ("Pool Stage", "S1")])

        outcomes = self.ground(championship, stage, explicit, structural, unrelated)

        # Heading + item under it: only when claimed as structural.
        self.assertEqual((outcomes["A1"], outcomes["A2"], outcomes["A3"]), (UNANCHORED, STRUCTURAL, UNANCHORED))

    def test_the_intent_naming_one_end_and_the_others_kind_supports_a_structural_claim(self):
        outcomes = self.ground(
            entity("E1", "2027 Championship", "championship", excerpt="2027 Championship", source_id="intent"),
            entity("E2", "Pool Stage", "stage"),
            assertion("A1", "E1", "includes stage", "E2", support="structural",
                      spans=[("stages listed in the flyer to the 2027 Championship", "intent"), ("Pool Stage", "S1")]),
        )

        self.assertEqual(outcomes["A1"], STRUCTURAL)

    def test_entities_and_facts_must_be_mentioned(self):
        outcomes = self.ground(
            entity("E9", "Wembley", "venue", excerpt="Eden Park | Auckland"),
            fact("F9", "E9", "Capacity", "90000", excerpt="Eden Park capacity: 50000"),
        )

        self.assertEqual((outcomes["E9"], outcomes["F9"]), (UNANCHORED, UNANCHORED))

    def test_unanchored_claims_never_reach_questions_or_compile(self):
        items = [i for i in self.flyer_items()] + [
            assertion("A99", "E2", "has match", "E6", hint="has_match", excerpt="Eden Park | Auckland | Opening match and final"),
        ]
        analysis = run_analysis(ReconcileState(frame=self.flyer_frame(), graph=graph(*items)),
                                index=SemanticModelIndex.load(self.model), bundle=self.bundle)

        self.assertNotIn("A99", analysis.assertions)
        self.assertEqual(analysis.ledger.get("ground:A99").outcome, UNANCHORED)
        change_set, trace = compile_change_set(analysis, index=SemanticModelIndex.load(self.model))
        self.assertEqual(check_trace(change_set, trace, analysis), [])


class CoverageTests(RugbyFixture):

    def setUp(self):
        super().setUp()
        self.bundle = EvidenceBundle.from_assets(FLYER_ASSETS)
        self.index = SemanticModelIndex.load(self.model)

    def coverage(self, items, dismissals=None):
        from ai.services.evidence_graph import resolve_graph_segments

        evidence = resolve_graph_segments(graph(*items), self.bundle)
        return compute_coverage(self.bundle, evidence, self.flyer_frame(), self.index, dismissals or {})

    def test_claimed_dismissed_and_uncovered_are_distinct(self):
        items = [entity("E6", "Eden Park", "venue", hint="venue", excerpt="Eden Park | Auckland"),
                 fact("F1", "E6", "City", "Auckland", excerpt="Eden Park | Auckland")]

        result = self.coverage(items, dismissals={"S1#4": {"reason": "not about the request", "count": 1}})

        self.assertEqual(result["S1#t1.r1"].status, CLAIMED)
        self.assertEqual(result["S1#4"].status, DISMISSED)
        self.assertTrue(result["S1#4"].flagged)  # it names Eden Park
        self.assertEqual(result["S1#2"].status, UNCOVERED)  # "... played at Eden Park"

    def test_an_entity_alone_does_not_account_for_a_relational_row(self):
        items = [entity("E6", "Eden Park", "venue", hint="venue", excerpt="Eden Park | Auckland")]

        self.assertEqual(self.coverage(items)["S1#t1.r1"].status, UNCOVERED)

    def test_a_dismissal_is_a_coverage_decision_never_a_claim(self):
        rs = ReconcileState(frame=self.flyer_frame(), graph=graph(*self.flyer_items()),
                            dismissals={"S1#4": {"reason": "irrelevant", "count": 2}})
        rs.graph.facts = [f for f in rs.graph.facts if f.fid != "F2"]

        analysis = run_analysis(rs, index=self.index, bundle=self.bundle)

        decision = analysis.ledger.get("cover:S1#4")
        self.assertEqual((decision.kind, decision.outcome), ("coverage", DISMISSED))
        self.assertIn("dismissed_target_evidence", decision.flags)
        self.assertFalse(analysis.ledger.rests_on_claim("cover:S1#4"))
        self.assertNotIn("S1#4", str([p.segment_id for i in analysis.graph.items() for p in i.provenance]))
        self.assertTrue(any("set aside as not relevant" in f.message for f in analysis.findings))


class HomonymAndMappingTests(RugbyFixture):

    def analyse(self, items, text):
        bundle = EvidenceBundle.from_assets([{"name": "notes.txt", "content": text}])
        return run_analysis(ReconcileState(frame=frame([target("T1", "stages", "stages")]), graph=graph(*items)),
                            index=SemanticModelIndex.load(self.model), bundle=bundle)

    def test_one_label_used_for_two_kinds_is_two_entities_without_a_question(self):
        text = "Stages: Pool Stage, Final.\n\nThe final is played at Eden Park."
        analysis = self.analyse([
            entity("E1", "Final", "stage", hint="stage", excerpt="Stages: Pool Stage, Final."),
            entity("E2", "Final", "match", hint="match", excerpt="The final is played at Eden Park."),
        ], text)

        self.assertEqual(len(analysis.clusters.clusters), 2)
        self.assertEqual(analysis.ledger.get("homonym:E1:E2").outcome, "distinct_kinds")
        self.assertFalse([question for question in analysis.questions if question.kind == "coreference"])

    def test_lexical_mapping_needs_the_predicate_in_the_cited_evidence(self):
        text = "Match 1 v Eden Park.\n\nMatch 2 is played at Eden Park."
        analysis = self.analyse([
            entity("E1", "Match 1", "match", hint="match", excerpt="Match 1"),
            entity("E2", "Match 2", "match", hint="match", excerpt="Match 2"),
            entity("E3", "Eden Park", "venue", hint="venue", excerpt="Eden Park is"),
            assertion("A1", "E1", "played at", "E3", excerpt="Match 1 v Eden Park"),
            assertion("A2", "E2", "played at", "E3", excerpt="Match 2 is played at Eden Park"),
        ], text)

        self.assertEqual(analysis.assertions["A1"].outcome, "ambiguous")
        self.assertEqual((analysis.assertions["A2"].outcome, analysis.assertions["A2"].basis), ("mapped", "lexical"))


class CardinalityTests(AIServiceTestCase):
    """Venue may host at most one Match (the shape of the live model)."""

    TEXT = "Match 1 is played at Sky Stadium.\n\nMatch 2 is played at Sky Stadium.\n\nMatch 3 was played at Sky Stadium until 2025."

    def setUp(self):
        self.model = self.make_model()
        match, venue = self.make_object_type(self.model, key="match"), self.make_object_type(self.model, key="venue")
        played_at = self.make_relationship_type(self.model, key="played_at")
        self.make_rule(played_at, match, venue, object_minimum=1, subject_minimum=1, subject_maximum=1)

    def analyse(self, *matches, pins=None):
        items = [entity("V", "Sky Stadium", "venue", hint="venue", excerpt="Sky Stadium")]
        for number, extra in matches:
            items += [entity(f"M{number}", f"Match {number}", "match", hint="match", excerpt=f"Match {number}"),
                      assertion(f"A{number}", f"M{number}", "is played at", "V", hint="played_at",
                                excerpt=f"Match {number} {'was' if extra else 'is'} played at Sky Stadium", **extra)]
        bundle = EvidenceBundle.from_assets([{"name": "notes.txt", "content": self.TEXT}])
        self.rs = ReconcileState(frame=frame([target("T1", "venues", "venues"), target("T2", "matches", "matches")]),
                                 graph=graph(*items), pins=pins or {})
        return run_analysis(self.rs, index=SemanticModelIndex.load(self.model), bundle=bundle)

    def test_simultaneous_satisfiers_above_the_maximum_are_a_constraint_conflict(self):
        analysis = self.analyse((1, {}), (2, {}))

        self.assertEqual({a for a, r in analysis.scope.excluded_assertions.items() if r == "constraint_conflict"}, {"A1", "A2"})
        self.assertFalse([question for question in analysis.questions if question.kind == "current_satisfier"])
        # The evidence exists; probing the requirement can't help. (Match 3's
        # sentence, which nothing extracted, is the venues target's own gap.)
        self.assertEqual([r.requirement_id for r in analysis.probe_requests], ["target:T1"])
        self.assertTrue(any(f.severity == "material" and "allows at most 1" in f.message for f in analysis.findings))
        change_set, _ = compile_change_set(analysis, index=SemanticModelIndex.load(self.model))
        self.assertFalse([a for a in change_set.actions if a.kind == "create_relationship"])

    def test_time_separated_satisfiers_keep_the_current_one(self):
        analysis = self.analyse((1, {}), (3, {"valid_to": "2025-01-01"}))

        self.assertEqual(analysis.scope.excluded_assertions, {"A3": "historical"})
        self.assertIn("A1", analysis.scope.selected_assertions)

    def test_within_the_maximum_nothing_is_excluded(self):
        analysis = self.analyse((1, {}))

        self.assertEqual(analysis.scope.excluded_assertions, {})
        self.assertIn("A1", analysis.scope.selected_assertions)


class InternationalFlyerFixture(AIServiceTestCase):
    """The live model's shape: a Venue hosts exactly one Match; a Match needs
    two Teams and a Venue; a Stage needs a Match."""

    INTENT = ("I want add the venues and stages listed in the flyer to my model, create any relationships that should be "
              "associated as well based on the information available")

    def setUp(self):
        self.model = self.make_model(name="Rugby")
        types = {k: self.make_object_type(self.model, key=k) for k in ("tournament", "stage", "match", "team", "venue")}
        rel = {k: self.make_relationship_type(self.model, key=k) for k in ("has_stage", "has_match", "has_team", "has_team_2", "played_at")}
        self.make_rule(rel["has_stage"], types["tournament"], types["stage"])
        self.make_rule(rel["has_match"], types["stage"], types["match"], object_minimum=1)
        self.make_rule(rel["has_team"], types["match"], types["team"], object_minimum=2)
        self.make_rule(rel["has_team_2"], types["tournament"], types["team"])
        self.make_rule(rel["played_at"], types["match"], types["venue"], object_minimum=1, subject_minimum=1, subject_maximum=1)
        self.assets = flyer_assets()
        self.bundle = EvidenceBundle.from_assets(self.assets)

    def seg(self, text):
        return next(s.segment_id for s in self.bundle.segments() if s.text.startswith(text))

    def frame(self):
        return frame([target("T1", "venues", "venues"), target("T2", "stages", "stages")],
                     include_related=True, include_related_excerpt="create any relationships that should be associated")

    def first_pass(self):
        """What the live run extracted: stages and venues, no matches."""

        items = []
        for number, (name, prefix) in enumerate((("Pool Stage", "- Pool Stage"), ("Quarter-finals", "- Quarter-finals"),
                                                 ("Semi-finals", "- Semi-finals"), ("Final", "- Final")), 1):
            items.append(entity(f"S{number}", name, "stage", hint="stage", excerpt=name, source_id="S1"))
            items[-1].provenance[0].segment_id = self.seg(prefix)
        for number, (name, city) in enumerate((("Eden Park", "Auckland"), ("Sky Stadium", "Wellington"),
                                                ("Forsyth Barr Stadium", "Dunedin"), ("FMG Stadium Waikato", "Hamilton"),
                                                ("McLean Park", "Napier"), ("Orangetheory Stadium", "Christchurch")), 1):
            row = self.seg(name + " |")
            items.append(entity(f"V{number}", name, "venue", hint="venue", excerpt=name))
            items[-1].provenance[0].segment_id = row
            items.append(fact(f"L{number}", f"V{number}", "Location", f"{city}, New Zealand", excerpt=f"{city}, New Zealand"))
            items[-1].provenance[0].segment_id = row
        return extraction(self.frame(), *items)

    def fixture_rows(self, payload):
        """The correction pass: what each uncovered fixture row says; other
        uncovered segments dismissed with a reason."""

        rows = {
            "Pool A | New Zealand v Fiji": ("PA", "Pool A", "New Zealand", "Fiji", "V1"),
            "Pool A | Japan v Samoa": ("PA", "Pool A", "Japan", "Samoa", "V2"),
            "Pool B | Australia v Argentina": ("PB", "Pool B", "Australia", "Argentina", "V3"),
            "Pool B | South Africa v Tonga": ("PB", "Pool B", "South Africa", "Tonga", "V4"),
        }
        items, dismissed, made = [], [], set()
        for number, entry in enumerate(payload["uncovered_segments"], 1):
            segment = entry["segment"]
            match_row = next((v for k, v in rows.items() if segment["text"].startswith(k)), None)
            if match_row is None:
                dismissed.append((segment["segment_id"], "Describes the format or results, not a specific venue or stage."))
                continue
            stage_id, stage, home, away, venue = match_row
            sid = segment["segment_id"]
            match = f"{home} v {away}"
            new = []
            if stage_id not in made:
                new.append(entity(stage_id, stage, "stage", hint="stage", excerpt=stage))
                made.add(stage_id)
            new += [
                entity(f"M{number}", match, "match", hint="match", excerpt=match),
                entity(f"H{number}", home, "team", hint="team", excerpt=home),
                entity(f"W{number}", away, "team", hint="team", excerpt=away),
                assertion(f"A{number}a", stage_id, "includes match", f"M{number}", hint="has_match", excerpt=f"{stage} | {match}"),
                assertion(f"A{number}b", f"M{number}", "is played by", f"H{number}", hint="has_team", excerpt=match),
                assertion(f"A{number}c", f"M{number}", "is played by", f"W{number}", hint="has_team", excerpt=match),
                assertion(f"A{number}d", f"M{number}", "is played at", venue, hint="played_at", excerpt=f"{match} | "),
            ]
            for item in new:
                for p in item.provenance:
                    p.segment_id = sid
            items += new
        for item in items:
            if hasattr(item, "aid") and item.aid.endswith("d"):
                item.provenance[0].excerpt = item.provenance[0].excerpt.rstrip(" |")
        return extraction(frame(), *items, dismissed=dismissed)

    @staticmethod
    def not_stated(payload):
        return probe(verdicts=[verdict(r["requirement_id"], "not_stated", segments_reviewed=r["segment_ids"]) for r in payload["requirements"]])

    def run_reconcile(self, provider):
        return run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=self.INTENT,
                                assets=self.assets, provider=provider)


class InternationalFlyerTests(InternationalFlyerFixture):

    def test_the_coverage_gate_recovers_the_fixture_table_and_the_result_is_honestly_partial(self):
        provider = ScriptedProvider([self.first_pass(), self.fixture_rows, self.not_stated, approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(provider.stages, ["extraction", "extraction_correction", "gap_probe", "verification"])
        # The live failure: no matches in the first pass. The fixture rows name
        # venues, so they were re-asked -- exactly those segments.
        reasked = [s["segment"]["segment_id"] for s in provider.payloads_for("extraction_correction")[0]["uncovered_segments"]]
        self.assertTrue({self.seg("Pool A | New Zealand v Fiji"), self.seg("Pool B | South Africa v Tonga")} <= set(reasked))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "partial")
        created = sorted(c.after["name"] for c in ProposalChange.objects.filter(proposal_id=result.proposal_id, target_type="Object"))
        self.assertTrue({"Eden Park", "Sky Stadium", "Forsyth Barr Stadium", "FMG Stadium Waikato", "Pool A", "Pool B",
                         "New Zealand v Fiji", "Japan v Samoa", "Fiji", "Tonga"} <= set(created), created)
        blocked = {b["target"] for b in result.blocked_targets}
        # Nothing invented to satisfy a rule: no match is identified for these.
        self.assertTrue({"McLean Park", "Pool Stage", "Semi-finals"} <= blocked, blocked)
        self.assertNotIn("McLean Park", created)

        probe_payload_sent = provider.payloads_for("gap_probe")[0]
        self.assertNotIn("played_at", str(probe_payload_sent))
        mclean = next(r for r in probe_payload_sent["requirements"] if "McLean Park" in r["question"])
        self.assertIn(self.seg("McLean Park |"), mclean["segment_ids"])
        self.assertTrue(all(s.startswith("S1#") for s in mclean["segment_ids"]))
        self.assertLess(sum(len(s["text"]) for s in probe_payload_sent["segments"]), len(self.bundle.sources[0].text))

    def test_a_zero_result_is_reviewed_and_a_missed_evidence_objection_recovers_it(self):
        def missed(payload):
            # The reviewer points at the fixture rows the extraction ignored.
            # The extraction dismissed it; the reviewer sees every dismissal.
            row = next(s for s in payload["dismissed_segments"] + payload["uncovered_segments"]
                       if s["text"].startswith("Pool B | South Africa v Tonga"))
            evidence = self.fixture_rows({"uncovered_segments": [{"segment": {"segment_id": row["segment_id"], "text": row["text"]}}]}).evidence
            evidence.entities = [e.model_copy(update={"eid": e.eid.replace("PB", "X0")}) if e.eid == "PB" else e for e in evidence.entities]
            for a in evidence.assertions:
                if a.subject_eid == "PB":
                    a.subject_eid = "X0"
            return reject(objection("segment", row["segment_id"], "missed_evidence", "The fixture table names the match at FMG Stadium Waikato.",
                                    evidence=evidence))

        only_fmg = frame([target("T1", "venues", "venues", hint="venue")])
        first = extraction(only_fmg, *[i for i in self.first_pass().evidence.items() if getattr(i, "eid", "") == "V4" or getattr(i, "fid", "") == "L4"])
        provider = ScriptedProvider([
            first,
            lambda payload: extraction(frame(), dismissed=[(s["segment"]["segment_id"], "not needed") for s in payload["uncovered_segments"]]),
            self.not_stated,
            missed,
            approve(),
        ])

        result = self.run_reconcile(provider)

        # Zero result -> Verification (not a terminal UNRESOLVED) -> routed back
        # -> recomputed -> compiled -> reviewed again.
        self.assertEqual(provider.stages, ["extraction", "extraction_correction", "gap_probe", "verification", "verification"])
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        created = {c.after["name"] for c in ProposalChange.objects.filter(proposal_id=result.proposal_id, target_type="Object")}
        self.assertIn("FMG Stadium Waikato", created)
        self.assertIn("South Africa v Tonga", created)

    @override_settings(AI_EXTRACTION_BATCH_MAX_CHARS=700)
    def test_large_evidence_is_extracted_in_batches_and_one_bad_batch_costs_no_other(self):
        def batch(payload):
            ids = {s["segment_id"] for s in payload["segments"]}
            first = payload["batch"]["number"] == 1
            items = [i for i in self.first_pass().evidence.items()
                     if not hasattr(i, "provenance") or not i.provenance or i.provenance[0].segment_id in ids]
            if payload["batch"]["number"] == 2:
                for item in items:
                    for p in item.provenance:
                        p.excerpt = "not in the source"
            return extraction(self.frame() if first else frame(), *items)

        def correction(payload):
            return extraction(frame(), dismissed=[(s["segment"]["segment_id"], "not needed") for s in payload["uncovered_segments"]])

        responders = {"extraction": batch, "extraction_correction": correction, "gap_probe": self.not_stated,
                      "adjudication": lambda p: answers(),
                      "verification": lambda p: approve()}
        provider = ScriptedProvider([lambda p: responders[p["stage"]](p)] * 20)
        batches = len(plan_batches(self.bundle, 700))

        self.run_reconcile(provider)

        self.assertGreater(batches, 1)
        self.assertEqual(provider.stages.count("extraction"), min(batches, 4))
        corrections = provider.payloads_for("extraction_correction")
        self.assertTrue(1 <= len(corrections) <= 2)
        invalid = {i["id"] for p in corrections for i in p["invalid_items"]}
        batch_two = {s["segment_id"] for s in provider.payloads_for("extraction")[1]["segments"]}
        expected = {i.eid if hasattr(i, "eid") else i.fid for i in self.first_pass().evidence.items()
                    if i.provenance and i.provenance[0].segment_id in batch_two}
        # Only the defective batch's claims were re-asked; every other batch
        # advanced and was frozen.
        self.assertTrue(invalid and invalid <= expected, (invalid, expected))
        sizes = [sum(len(s["text"]) for s in p["segments"]) for p in provider.payloads_for("extraction")]
        self.assertTrue(all(size <= 700 for size in sizes), sizes)

    def test_probe_packs_are_local_and_carry_no_ontology_keys(self):
        rs = ReconcileState(frame=self.frame(), graph=self.first_pass().evidence)
        analysis = run_analysis(rs, index=SemanticModelIndex.load(self.model), bundle=self.bundle)
        mclean = next(r for r in analysis.probe_requests if analysis.cluster_name(r.cluster_id) == "McLean Park")

        requirements, segments, coverage = probe_payload([mclean], analysis, index=SemanticModelIndex.load(self.model), bundle=self.bundle)

        row = self.bundle.segment(self.seg("McLean Park |"))
        # Its row, plus the heading/table segments it sits under -- nothing else.
        self.assertEqual([s["segment_id"] for s in segments], [*row.ancestor_ids, row.segment_id])
        self.assertEqual(coverage[mclean.requirement_id], "complete")
        self.assertEqual(requirements[0]["looking_for"]["relationship"], "Played At")
        self.assertNotIn("played_at", str({k: v for k, v in requirements[0].items() if not k.startswith("_")}))


@unittest.skipUnless(os.environ.get("ONYXJAR_LIVE_AI_TESTS") == "1", "Set ONYXJAR_LIVE_AI_TESTS=1 to run against the real provider.")
class LiveInternationalFlyerTests(InternationalFlyerFixture):
    """
    Opt-in, real-provider run of the international flyer (the live failure).
    Asserts invariants only and prints what to measure: matches extracted
    from fixture rows, coverage (claimed / dismissed / uncovered), grounding
    rejections, probe pack sizes and verdicts, calls/tokens, completeness.
    """

    def test_live_international_flyer(self):
        from ai.models import AIExecution, AIExecutionStep

        result = self.run_reconcile(None)

        self.assertEqual(result.execution_status.value, "completed", result)
        self.assertLessEqual(result.provider_calls, settings.AI_WORKFLOW_MAX_PROVIDER_CALLS + settings.AI_TERMINAL_EXPLANATION_MAX_CALLS)
        execution = AIExecution.objects.get(pk=result.execution_id)
        steps = AIExecutionStep.objects.filter(execution=execution)
        print("\nLIVE INTERNATIONAL FLYER:", result.outcome.value, result.completeness, result.stage_summary,
              "tokens:", (execution.usage or {}).get("total_tokens"))
        print("  steps:", [(s.stage, s.decision) for s in steps])
        for finding in result.findings:
            print("  finding:", finding.severity, finding.message)
        for blocked in result.blocked_targets:
            print("  blocked:", blocked["type_key"], blocked["target"], blocked["missing_requirements"])
        if result.proposal_id:
            for change in ProposalChange.objects.filter(proposal_id=result.proposal_id):
                print("  ", change.operation, change.target_type, change.after)
        if settings.AI_TRACE_DIR:
            from ai.services.tracing import fate_table, load

            steps = load(f"{settings.AI_TRACE_DIR}/{result.execution_id}")
            snapshot = next((s["snapshot"] for s in reversed(steps) if s["kind"] == "deterministic"), {})
            print(f"  trace: {settings.AI_TRACE_DIR}/{result.execution_id}")
            for row in fate_table(snapshot):
                print("  fate:", row)
