"""
Reconcile as a bounded convergence process (ai/README.md, "Convergence"):
every stage returns to analysis, which routes whatever new work exists to the
stage that resolves it -- decision gaps to Adjudication, evidence gaps to the
Gap Probe, objections back through their producer -- each class of work under
its own budget, the run bounded overall, and anything left over reported
honestly (deferred, never defaulted).

Classes of behaviour, not rugby strings: the scenarios run on the small
rugby flyer, and the regression replays the captured live GPT-4.1 run of the
international flyer (ai/tests/fixtures/traces/international_flyer_gpt41)
through the corrected router.
"""

import json
import re
import tempfile
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import get_args

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from model.models.proposal import ProposalChange
from model.models.relationship_type_rule import RelationshipTypeRule

from ai.models import AIExecutionStep
from ai.services.evidence_bundle import EvidenceBundle
from ai.services.reconcile import questions as q
from ai.services.reconcile.analysis import run_analysis
from ai.services.reconcile.responses import AdjudicationAnswer, AdjudicationResult, Citation
from ai.services.reconcile.state import ReconcileState
from ai.services.result_schema import OperationOutcome
from ai.services.semantic.index import SemanticModelIndex, normalize_name
from ai.services.tracing import ReplayProvider, load, request_of
from ai.services.workflow.engine import WorkflowDefinition, WorkflowRun
from ai.tests.rugby import RugbyFixture
from ai.tests.support import (
    ScriptedProvider,
    approve,
    assertion,
    entity,
    extraction,
    frame,
    graph,
    objection,
    probe,
    reject,
    target,
    verdict,
)
from ai.tests.test_evidence_lifecycle import InternationalFlyerFixture, flyer_assets
from ai.tests.test_reconcile_workflow import ReconcileWorkflowTestCase

TRACE = Path(__file__).parent / "fixtures" / "traces" / "international_flyer_gpt41"
# Live run bb3535b7 (provider outputs only).
TRACE_LATE_ROUND = Path(__file__).parent / "fixtures" / "traces" / "international_flyer_bb3535b7"
TRACE_OPEN_TEAMS = Path(__file__).parent / "fixtures" / "traces" / "international_flyer_f3e0d659"
TRACE_EMPTY_FOUND = Path(__file__).parent / "fixtures" / "traces" / "international_flyer_7f0fcac7"
TRACE_NO_TEAMS = Path(__file__).parent / "fixtures" / "traces" / "international_flyer_3f801647"
TRACE_REUSED_IDS = Path(__file__).parent / "fixtures" / "traces" / "international_flyer_286357bd"

INCLUDES = "predicate_mapping:include:stage:match"
PLAYED_BY = "predicate_mapping:is_played_by:match:team"


def cite(*answers):
    """answers: (question_id, option_id, segment_id, excerpt)."""

    return AdjudicationResult(answers=[
        AdjudicationAnswer(question_id=qid, option_id=option, citations=[Citation(segment_id=sid, excerpt=excerpt)])
        for qid, option, sid, excerpt in answers
    ])


class ConvergenceScenario(ReconcileWorkflowTestCase):
    """Wave 1: the stage->match wording is undecided (no hint), so Pool
    Stage's requirement is a DECISION gap. Once answered, Match 1 is needed
    and its second team is missing: an EVIDENCE gap. The probe recovers Fiji
    in its own (hint-stripped) wording: a new decision gap -> Adjudication
    again."""

    def setUp(self):
        super().setUp()
        self.trace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.trace_dir.cleanup)
        tracing = override_settings(AI_TRACE_DIR=self.trace_dir.name)
        tracing.enable()
        self.addCleanup(tracing.disable)

    def first_wave(self, *, include_fiji=False):
        items = self.flyer_items(include_fiji=include_fiji)
        next(i for i in items if getattr(i, "aid", "") == "A2").relationship_type_hint = None
        return extraction(self.flyer_frame(), *items)

    def has_team_requirement(self):
        return "req:E3:{}:subject".format(RelationshipTypeRule.objects.get(relationship_type=self.has_team).id)

    def fiji_probe(self):
        return probe(
            entity("X1", "Fiji", "team", excerpt="New Zealand v Fiji"),
            assertion("X2", "E3", "is played by", "X1", excerpt="Match 1: New Zealand v Fiji"),
            verdicts=[verdict(self.has_team_requirement(), "found", claim_ids=["X2"], segments_reviewed=["S1#2"])],
        )

    def includes_answer(self, excerpt="Pool Stage"):
        return cite((INCLUDES, "has_match:as_stated", "S1#2", excerpt))

    def played_by_answer(self):
        return cite((PLAYED_BY, "has_team:as_stated", "S1#2", "New Zealand v Fiji"))

    def snapshots(self, result):
        return [s for s in load(Path(self.trace_dir.name) / str(result.execution_id)) if s["kind"] == "deterministic"]

    def routes(self, result):
        return [s["snapshot"]["work_queue"]["route"] for s in self.snapshots(result) if s["stage"] == "analysis"]


class ConvergenceTests(ConvergenceScenario):

    def test_a_probe_raises_a_decision_that_is_adjudicated_and_then_compiled(self):
        provider = ScriptedProvider([self.first_wave(), self.includes_answer(), self.fiji_probe(), self.played_by_answer(), approve()])

        result = self.run_reconcile(provider)

        # 1-2. The probe's claim raises a new (pattern) decision gap, routed to Adjudication.
        after_probe = next(s["snapshot"] for s in self.snapshots(result) if s["stage"] == "analysis" and "X2" in s["snapshot"]["graph_ids"])
        self.assertEqual(after_probe["work_queue"]["route"], "adjudication")
        self.assertEqual(after_probe["work_queue"]["decision_gaps"], [PLAYED_BY])
        self.assertIn("X2", next(x["subject_ids"] for x in after_probe["questions"] if x["question_id"] == PLAYED_BY))
        # 3. Resolved: a claimed pin, and the mapping rests on it.
        final = self.snapshots(result)[-1]["snapshot"]
        self.assertEqual(final["pins"][PLAYED_BY], {"option_id": "has_team:as_stated", "basis": "adjudicated"})
        mapping = next(d for d in final["ledger"] if d["decision_id"] == "map:X2")
        self.assertEqual(mapping["outcome"], "mapped")
        self.assertIn(f"adj:{PLAYED_BY}", mapping["inputs"])
        # 4. Analysis re-runs after every Adjudication before anything compiles.
        steps = [s.stage for s in AIExecutionStep.objects.filter(execution_id=result.execution_id)]
        self.assertEqual(steps, ["extraction", "analysis", "adjudication", "analysis", "gap_probe", "analysis", "adjudication", "analysis",
                                 "compile", "verification"])
        # 5. Compile receives the resolved result, traced to the answer.
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "complete")
        self.assertIn("Fiji", self.created_names(result))
        traced = {d for change in provider.payloads_for("verification")[0]["changes"] for d in change["decision_ids"]}
        self.assertIn("map:X2", traced)  # which rests on adj:<question> (above)

    def test_adjudication_is_re_entered_and_a_probe_follows_an_answer(self):
        provider = ScriptedProvider([self.first_wave(), self.includes_answer(), self.fiji_probe(), self.played_by_answer(), approve()])

        result = self.run_reconcile(provider)

        # 6-7. Adjudication twice, with a probe between that only the first answer made necessary.
        self.assertEqual(provider.stages, ["extraction", "adjudication", "gap_probe", "adjudication", "verification"])
        self.assertEqual(self.routes(result), ["adjudication", "gap_probe", "adjudication", "compile"])
        # Pool Stage's undecided "includes" is a decision gap: never probed.
        probed = [r["requirement_id"] for r in provider.payloads_for("gap_probe")[0]["requirements"]]
        self.assertEqual(probed, [self.has_team_requirement()])
        self.assertEqual(result.stage_summary["adjudication"]["calls"], 2)

    def test_each_question_carries_its_own_citable_segments(self):
        provider = ScriptedProvider([self.first_wave(), self.includes_answer(), self.fiji_probe(), self.played_by_answer(), approve()])

        self.run_reconcile(provider)

        payload = provider.payloads_for("adjudication")[0]
        self.assertEqual(payload["questions"][0]["segment_ids"], ["S1#2"])
        # The segment and the heading it sits under, citable by id -- not the raw source.
        self.assertEqual([s["segment_id"] for s in payload["segments"]], ["S1#1", "S1#2"])
        self.assertNotIn("evidence", payload)


class BudgetTests(ConvergenceScenario):

    def test_a_correction_never_consumes_a_round(self):
        provider = ScriptedProvider([
            self.first_wave(), self.includes_answer(excerpt="Pool Stage | Match 1"), self.includes_answer(),
            self.fiji_probe(), self.played_by_answer(), approve(),
        ])

        result = self.run_reconcile(provider)

        self.assertEqual(provider.stages, ["extraction", "adjudication", "adjudication", "gap_probe", "adjudication", "verification"])
        self.assertEqual(result.stage_summary["adjudication"]["calls"], 2)
        self.assertEqual(result.stage_summary["adjudication_correction"]["calls"], 1)
        feedback = provider.payloads_for("adjudication")[1]["feedback"][0]
        self.assertEqual(feedback["code"], "excerpt_not_found")
        self.assertIn("Keep your choice", feedback["message"])
        self.assertEqual(result.completeness, "complete")

    # 3 calls used after the probe; another Adjudication round needs itself
    # and a full Verification pass (review + its correction): 3 > 5 - 3.
    @override_settings(AI_WORKFLOW_MAX_PROVIDER_CALLS=5)
    def test_a_round_the_run_cannot_afford_is_deferred_without_defaulting(self):
        provider = ScriptedProvider([self.first_wave(), self.includes_answer(), self.fiji_probe(), approve()])

        result = self.run_reconcile(provider)

        # 8. Only Adjudication stopped; the probe still ran.
        self.assertEqual(provider.stages, ["extraction", "adjudication", "gap_probe", "verification"])
        final = self.snapshots(result)[-1]["snapshot"]
        # Deferred, never pinned: no budget default anywhere.
        self.assertNotIn(PLAYED_BY, final["pins"])
        self.assertFalse([p for p in final["pins"].values() if p["basis"] == "budget"])
        self.assertEqual(final["work_queue"]["deferred_decisions"], [PLAYED_BY])
        ledger = {d["decision_id"]: d for d in provider.payloads_for("verification")[0]["decision_ledger"]}
        self.assertEqual((ledger[f"open:{PLAYED_BY}"]["outcome"], ledger[f"open:{PLAYED_BY}"]["basis"]), ("unadjudicated", "budget"))
        self.assertNotIn(f"adj:{PLAYED_BY}", ledger)
        # 10. Honest termination: evidence stated, decision not adjudicated.
        self.assertEqual([d["question_id"] for d in provider.payloads_for("verification")[0]["open_decisions"]], [PLAYED_BY])
        self.assertEqual(result.completeness, "partial")
        missing = next(m for b in result.blocked_targets for m in b["missing_requirements"] if m.get("entity") == "Match 1")
        self.assertEqual((missing["evidenced"], missing["viable"], missing["pending_decision"]), (2, 1, {"open": 1}))
        message = next(f.message for f in result.findings if "Pool Stage" in f.message)
        self.assertIn("not adjudicated", message)
        self.assertNotIn("the evidence identifies", message)

    def test_an_answer_refused_twice_is_recorded_never_relied_on(self):
        bad = self.includes_answer(excerpt="Pool Stage | Match 1")
        provider = ScriptedProvider([self.first_wave(), bad, bad, approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(provider.stages, ["extraction", "adjudication", "adjudication", "verification"])
        final = self.snapshots(result)[-1]["snapshot"]
        self.assertEqual(final["pins"][INCLUDES]["basis"], "rejected_answer")
        ledger = {d["decision_id"]: d for d in provider.payloads_for("verification")[0]["decision_ledger"]}
        self.assertEqual(ledger[f"open:{INCLUDES}"]["outcome"], "rejected_answer")
        self.assertNotIn(f"adj:{INCLUDES}", ledger)
        self.assertEqual([b["target"] for b in result.blocked_targets], ["Pool Stage"])
        self.assertTrue(any("could not be verified" in f.message for f in result.findings), self.messages(result))

    @override_settings(AI_WORKFLOW_MAX_PROVIDER_CALLS=3)
    def test_the_whole_run_stays_globally_bounded(self):
        provider = ScriptedProvider([self.first_wave(), approve()])

        result = self.run_reconcile(provider)

        # No recovery round fits beside a full Verification pass: the decision
        # is deferred (never defaulted) and the review still runs.
        self.assertEqual(provider.stages, ["extraction", "verification"])
        self.assertLessEqual(result.provider_calls, 3)
        final = self.snapshots(result)[-1]["snapshot"]
        self.assertEqual(final["work_queue"]["deferred_decisions"], [INCLUDES])
        self.assertNotIn(INCLUDES, final["pins"])
        self.assertEqual(result.completeness, "partial")
        deterministic = AIExecutionStep.objects.filter(execution_id=result.execution_id, provider_call=False).count()
        self.assertLessEqual(deterministic, settings.AI_WORKFLOW_MAX_DETERMINISTIC_STEPS)


class EngineBudgetKeyTests(SimpleTestCase):

    def run_with(self, budgets, calls=None):
        definition = WorkflowDefinition(stages={}, first_stage="x", stage_budgets=budgets, total_budget=10, explanation_budget=1)
        return WorkflowRun(operation=None, model=None, user=None, intent=None, bundle=None, provider=None, config=None,
                           execution=None, definition=definition, stage_calls=dict(calls or {}))

    def test_corrections_are_charged_to_their_own_budget_when_declared(self):
        run = self.run_with({"adjudication": 1, "adjudication_correction": 1, "planning": 3}, {"adjudication": 1})

        self.assertFalse(run.allows("adjudication"))
        self.assertTrue(run.allows("adjudication", correction=True))
        # Without a declared correction budget, a correction is a call of the stage (Create's planning).
        self.assertEqual(run.budget_key("planning", True), "planning")


class VerificationReentryTests(ConvergenceScenario):

    def test_missed_evidence_re_enters_the_loop_through_adjudication(self):
        missed = objection("segment", "S1#2", "missed_evidence", "Fiji also plays Match 1.", evidence=graph(
            entity("X1", "Fiji", "team", excerpt="New Zealand v Fiji"),
            assertion("X2", "E3", "is played by", "X1", excerpt="Match 1: New Zealand v Fiji"),
        ))
        not_stated = probe(verdicts=[verdict(self.has_team_requirement(), "not_stated", segments_reviewed=["S1#2"])])
        provider = ScriptedProvider([
            self.flyer_extraction(include_fiji=False), not_stated, reject(missed), self.played_by_answer(), approve(),
        ])

        result = self.run_reconcile(provider)

        # 9. Objection -> producer (a claim) -> analysis -> new decision gap -> Adjudication -> compile -> review.
        self.assertEqual(provider.stages, ["extraction", "gap_probe", "verification", "adjudication", "verification"])
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "complete")
        self.assertIn("Fiji", self.created_names(result))

    def test_a_reviewer_answer_to_a_decision_must_quote_the_evidence(self):
        unquoted = objection("decision", "map:A5", "wrong_mapping", "It is the converse.", option_id="played_at:as_stated", excerpt="nowhere")
        provider = ScriptedProvider([self.flyer_extraction(), reject(unquoted), approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(provider.stages, ["extraction", "verification", "verification"])
        feedback = provider.payloads_for("verification")[1]["feedback"][0]
        self.assertEqual(feedback["code"], "unroutable_objection")
        self.assertIn("Quote", feedback["message"])
        self.assertEqual(result.stage_summary["verification_correction"]["calls"], 1)
        self.assertEqual(result.stage_summary["verification"]["calls"], 1)


class DecisionGapUnitTests(RugbyFixture):

    TEXT = "Pool Stage\nMatch 1: New Zealand v Fiji, played at Eden Park\nEden Park hosts Match 1"

    def analyse(self, items, pins=None):
        bundle = EvidenceBundle.from_assets([{"name": "notes.txt", "content": self.TEXT}])
        state = ReconcileState(frame=frame([target("T1", "matches", "matches")]), graph=graph(*items), pins=dict(pins or {}))
        return run_analysis(state, index=SemanticModelIndex.load(self.model), bundle=bundle)

    def match_items(self, *extra):
        return [
            entity("E1", "Match 1", "match", hint="match", excerpt="Match 1"),
            entity("E2", "Eden Park", "venue", hint="venue", excerpt="Eden Park"),
            entity("E3", "New Zealand", "team", hint="team", excerpt="New Zealand"),
            entity("E4", "Fiji", "team", hint="team", excerpt="Fiji"),
            assertion("A1", "E1", "has team", "E3", hint="has_team", excerpt="Match 1: New Zealand v Fiji"),
            assertion("A2", "E1", "has team", "E4", hint="has_team", excerpt="Match 1: New Zealand v Fiji"),
            *extra,
        ]

    def requirement(self, analysis, eid, relationship_type):
        return next(r for r in analysis.scope.requirements[analysis.clusters.by_eid[eid]] if str(r.relationship_type_id) == str(relationship_type.id))

    def test_undecided_evidence_is_evidenced_but_never_viable_and_never_probed(self):
        analysis = self.analyse(self.match_items(assertion("A3", "E1", "is held at", "E2", excerpt="Match 1: New Zealand v Fiji, played at Eden Park")))

        requirement = self.requirement(analysis, "E1", self.played_at)
        self.assertEqual(requirement.pending_decision, ["A3"])
        self.assertEqual((requirement.evidenced, requirement.viable_count), (1, 0))
        self.assertNotIn(requirement.requirement_id, [r.requirement_id for r in analysis.probe_requests])
        self.assertTrue(analysis.questions)

    def test_a_rejected_answer_never_displaces_a_hint(self):
        hinted = assertion("A3", "E1", "is held at", "E2", hint="played_at", excerpt="Match 1: New Zealand v Fiji, played at Eden Park")
        pins = {q.key("assertion_mapping", "A3"): q.Pin(option_id=q.UNDECIDABLE, basis="rejected_answer", reason="bad quote")}

        analysis = self.analyse(self.match_items(hinted), pins=pins)

        self.assertEqual((analysis.assertions["A3"].outcome, analysis.assertions["A3"].basis), ("mapped", "hint"))

    def test_two_statements_of_one_relationship_are_one_counterpart(self):
        analysis = self.analyse(self.match_items(
            assertion("A3", "E1", "played at", "E2", hint="played_at", excerpt="played at Eden Park"),
            assertion("A4", "E2", "hosts", "E1", hint="played_at", orientation="converse", excerpt="Eden Park hosts Match 1"),
        ))

        requirement = self.requirement(analysis, "E1", self.played_at)
        self.assertEqual(sorted(requirement.candidates), ["A3", "A4"])
        self.assertEqual(requirement.evidenced, 1)
        self.assertFalse(analysis.scope.constraint_conflicts)

    def test_two_statements_about_one_team_do_not_meet_a_minimum_of_two(self):
        analysis = self.analyse([
            *self.match_items()[:3],
            assertion("A1", "E1", "has team", "E3", hint="has_team", excerpt="Match 1: New Zealand v Fiji"),
            assertion("A2", "E1", "is played by", "E3", hint="has_team", excerpt="Match 1: New Zealand v Fiji"),
            assertion("A3", "E1", "played at", "E2", hint="played_at", excerpt="played at Eden Park"),
        ])

        requirement = self.requirement(analysis, "E1", self.has_team)
        self.assertEqual(requirement.viable_count, 1)
        self.assertNotIn(analysis.clusters.by_eid["E1"], analysis.scope.viable)


class CorroborationTests(ReconcileWorkflowTestCase):

    def test_a_relationship_stated_twice_is_one_change_citing_both(self):
        both = self.flyer_extraction()
        both.evidence.assertions.append(
            assertion("A7", "E6", "hosts", "E3", hint="played_at", orientation="converse", excerpt="Match 1: New Zealand v Fiji, played at Eden Park")
        )
        provider = ScriptedProvider([both, approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(result.completeness, "complete")
        played_at = [c for c in provider.payloads_for("verification")[0]["changes"] if {"map:A5", "map:A7"} & set(c["decision_ids"])]
        self.assertEqual(len(played_at), 1)
        self.assertTrue({"map:A5", "map:A7"} <= set(played_at[0]["decision_ids"]))


def no_longer_asked(step: Path) -> bool:
    """A captured Adjudication round that asked only indirect_classification
    questions: those are never asked now (their answer cannot change what is
    decided -- ai.services.reconcile.analysis._questions), so the round is not
    replayed."""

    data = json.loads(step.read_text(encoding="utf-8"))
    answers = (data.get("output") or {}).get("answers") or []
    return data.get("stage") == "adjudication" and bool(answers) and all(
        a["question_id"].startswith("indirect_classification:") for a in answers)


def single_option_oracle(payload):
    """A stand-in adjudicator for the counterfactual replay: answers each
    question that has exactly one substantive option, citing the first
    segment the question lists; otherwise 'undecidable'."""

    segments = {s["segment_id"]: s["text"] for s in payload["segments"]}
    answers = []
    for question in payload["questions"]:
        options = [o["option_id"] for o in question["options"] if o["option_id"] not in (q.NONE, q.UNDECIDABLE)]
        sid = next(iter(question["segment_ids"]), None)
        if len(options) != 1 or sid is None:
            answers.append({"question_id": question["question_id"], "option_id": q.UNDECIDABLE})
            continue
        answers.append({"question_id": question["question_id"], "option_id": options[0],
                        "citations": [{"segment_id": sid, "excerpt": segments[sid]}]})
    return {"answers": answers}


def no_more_claims(payload):
    return {"claims": {}, "verdicts": []}


def nothing_found(payload):
    """A probe responder for rounds the captured run never made: the
    segments state nothing for any requirement."""

    return {"claims": {}, "verdicts": [{"requirement_id": r["requirement_id"], "status": "not_stated"} for r in payload["requirements"]]}


def no_more_corrections(payload):
    """A continuation for a correction stage whose captured round wasn't the
    last: offers nothing further, withdrawing whatever is still pending."""

    return {"intent_frame": {}, "evidence": {}, "dismissed_segments": []}



class LiveFlyerRegressionTests(InternationalFlyerFixture):
    """The captured live GPT-4.1 run (every venue/stage/match blocked, then
    approved): its provider outputs replayed by stage through the corrected
    router. Where the corrected routing asks for a call the live run never
    made (the later Adjudication rounds; a probe correction for requirements
    now re-probed), a stand-in answers it."""

    LIVE_RULE_IDS = {
        "08d55888-57fd-4b34-a965-6ce348ee1af0": "played_at",
        "d210e934-4d66-478d-b37d-6fa0392fc9a0": "has_match",
        "bdc1065c-e2cc-4337-8b68-d9ba98443331": "has_team",
    }

    def replay(self):
        # Requirement ids embed rule ids, which differ per database.
        rules = {r.relationship_type.key: str(r.id) for r in RelationshipTypeRule.objects.filter(relationship_type__model=self.model)}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for step in TRACE.glob("*.json"):
            if no_longer_asked(step):
                continue
            text = step.read_text(encoding="utf-8")
            for live, key in self.LIVE_RULE_IDS.items():
                text = text.replace(live, rules[key])
            (Path(directory.name) / step.name).write_text(text, encoding="utf-8")
        provider = ReplayProvider(directory.name, inject={"adjudication": [single_option_oracle] * 4,
                                                          "gap_probe": [nothing_found] * 3,
                                                          "gap_probe_correction": [no_more_claims] * 4,
                                                          "extraction_correction": [no_more_corrections] * 3})
        return provider, self.run_reconcile(provider)

    def changes(self, result):
        return list(ProposalChange.objects.filter(proposal_id=result.proposal_id))

    def test_probe_claims_re_enter_adjudication_and_compile(self):
        provider, result = self.replay()

        self.assertEqual(provider.requested, [
            # The segment re-asks, then the second wave: invalid claims first
            # produced by the segment re-asks get their own re-ask. (The first
            # wave's item re-ask is gone: its items were unanchored claims no
            # segment could anchor, dropped without one.)
            "extraction", "extraction_correction", "extraction_correction",
            # (The live run's first Adjudication round and its correction asked
            # only indirect_classification questions, which are never asked now.)
            # Each probe round's output gets its own correction (round 2's is no
            # longer spent by round 1's).
            "gap_probe", "gap_probe_correction", "adjudication", "gap_probe", "gap_probe_correction", "adjudication", "verification",
        ])
        self.assertLessEqual(result.provider_calls, settings.AI_WORKFLOW_MAX_PROVIDER_CALLS + settings.AI_TERMINAL_EXPLANATION_MAX_CALLS)
        # The request itself drives the search: the elided target excerpts are
        # repaired, so the venues/stages targets are kept -- and the rows nothing
        # accounted for are their gaps -- instead of an empty frame widening
        # scope to everything.
        first_probe = provider.payloads[provider.requested.index("gap_probe")]
        self.assertTrue({"target:T1", "target:T2"} <= {r["requirement_id"] for r in first_probe["requirements"]})
        verification = provider.payloads[provider.requested.index("verification")]
        # Venues compile; every stage evidenced is blocked, so the stages
        # target is reported as blocked -- never "evidenced" with nothing done.
        self.assertEqual({t["target_id"]: t["status"] for t in verification["intent_targets"]}, {"T1": "evidenced", "T2": "blocked"})
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "partial")
        self.assertEqual((result.stage_summary["adjudication"]["calls"], result.stage_summary.get("adjudication_correction", {}).get("calls", 0)), (2, 0))
        created = {c.after["name"] for c in self.changes(result) if c.target_type == "Object" and c.operation == "create"}
        self.assertTrue({"Eden Park", "Sky Stadium", "Forsyth Barr Stadium", "FMG Stadium Waikato", "New Zealand v Fiji",
                         "Japan v Samoa", "Australia v Argentina", "South Africa v Tonga", "Fiji", "Tonga"} <= created, created)
        # "Eden Park hosts match NZ v Fiji" (probe 1) and "NZ v Fiji played at Eden Park" (probe 2): one change.
        verification = provider.payloads[provider.requested.index("verification")]
        corroborated = [c for c in verification["changes"] if {"map:A12", "map:A21"} <= set(c["decision_ids"])]
        self.assertEqual(len(corroborated), 1)

    def test_what_stays_blocked_is_what_no_claim_states(self):
        _, result = self.replay()

        for blocked in result.blocked_targets:
            for missing in blocked["missing_requirements"]:
                # Nothing stays blocked on an undecided mapping once Adjudication had rounds left.
                self.assertFalse(missing["pending_decision"], blocked)
        # No captured claim relates any stage to a match: honestly blocked.
        self.assertIn("Pool Stage", [b["target"] for b in result.blocked_targets])

    def test_an_unsupported_found_is_re_probed_once_with_the_reason(self):
        provider, _ = self.replay()

        first, second = [p for p in provider.payloads if p["stage"] == "gap_probe"]
        pool_a = next(r for r in first["requirements"] if r["entity"]["name"] == "Pool A")
        again = next(r for r in second["requirements"] if r["requirement_id"] == pool_a["requirement_id"])
        self.assertIn("do not relate 'Pool A' to any Match", again["previous_answer"])
        self.assertNotIn("previous_answer", pool_a)

    # After the first probe round (+ correction), one Adjudication round and
    # the second probe round, 8 of 10 calls are spent: no further round leaves
    # a full Verification pass, so later questions are deferred.
    @override_settings(AI_WORKFLOW_MAX_PROVIDER_CALLS=10)
    def test_a_run_cut_short_by_its_budget_ends_honestly(self):
        provider, result = self.replay()

        # One round; later questions are deferred, never defaulted.
        self.assertEqual(provider.requested.count("adjudication"), 1)
        self.assertEqual(provider.requested[-1], "verification")
        verification = provider.payloads[provider.requested.index("verification")]
        self.assertTrue(verification["open_decisions"])
        self.assertFalse([d for d in verification["decision_ledger"] if d["decision_id"].startswith("adj:") and d.get("basis") == "budget"])
        messages = [f.message for f in result.findings if f.severity == "material"]
        eden = next(m for m in messages if "'Eden Park'" in m)
        self.assertIn("relates it to 1 match(s)", eden)  # two statements, one match
        self.assertIn("not adjudicated", eden)
        self.assertNotIn("the evidence identifies 0", eden)


class IdTranslatingReplay(ReplayProvider):
    """A captured run replayed into a run whose global ids may differ: ingress
    never reuses an id with a history (ai.services.reconcile.ingress), so an
    entity the live run happened to file under a reused id gets a fresh one
    here. A captured reference to an entity id this run has not shown the
    model is translated to the id this run shows for the same-named entity --
    the id the live model would have used, having been shown it."""

    def __init__(self, path, **kwargs):
        super().__init__(path, **kwargs)
        self.captured_names = {}
        for step in self.steps:
            graph = step["output"].get("evidence") or step["output"].get("claims") or {}
            for entity in graph.get("entities") or []:
                self.captured_names.setdefault(entity["eid"], normalize_name(entity["name"]))

    def generate_structured(self, *, system_prompt, user_payload, response_schema, config):
        result = super().generate_structured(system_prompt=system_prompt, user_payload=user_payload,
                                             response_schema=response_schema, config=config)
        output = result.parsed.model_dump(mode="json")
        graph = output.get("evidence") or output.get("claims") or {}
        shown = [*(user_payload.get("already_extracted") or {}).get("entities", []), *(user_payload.get("known_entities") or [])]
        shown_ids = {e["eid"] for e in shown} | {a["aid"] for a in (user_payload.get("already_extracted") or {}).get("assertions", [])}
        by_name = {normalize_name(e["name"]): e["eid"] for e in shown}
        defined = {e["eid"] for e in graph.get("entities") or []}

        def translate(ref):
            if ref in defined or ref in shown_ids:
                return ref
            return by_name.get(self.captured_names.get(ref), ref)

        for assertion_ in graph.get("assertions") or []:
            assertion_["subject_eid"], assertion_["object_eid"] = translate(assertion_["subject_eid"]), translate(assertion_["object_eid"])
        for fact in graph.get("facts") or []:
            fact["subject_id"] = translate(fact["subject_id"])
        for verdict_ in output.get("verdicts") or []:
            verdict_["claim_ids"] = [translate(c) for c in verdict_["claim_ids"]]
            verdict_["candidate_eids"] = [translate(c) for c in verdict_["candidate_eids"]]
        return replace(result, parsed=response_schema.model_validate(output))


# -- replay keyed by the work asked for ---------------------------------------------
#
# A captured run replayed through a workflow that no longer makes every call
# it made: each call is answered from the captured call that was asked the
# same work, so a call that no longer happens does not shift later captured
# outputs onto the wrong request (captured steps record their `request`):
#
#     reading                 the first unused captured call that read one of
#                             the elements asked, restricted to those elements
#                             (a correction no longer needed is skipped over)
#     adjudication            each question answered from the captured answer
#                             to that question id; questions no captured run
#                             answered get the single-option stand-in
#     gap_probe /             the first unused captured call of the stage whose
#     *_correction            recorded request shares work with this one (an
#                             item, segment or requirement id); captured calls
#                             skipped over are calls that no longer happen.
#                             A corrected item is served only to a call that
#                             re-asks it, verdicts only for requirements asked
#     extraction /            in captured order
#     verification
#
# Calls with no captured counterpart get the stand-ins above.


# The ids of the work a request asks for -- the same shape as a captured
# step's recorded `request` (ai.services.tracing.request_of).
_work = request_of


def _ids(work) -> set:
    return {(kind, identifier) for kind, ids in work.items() for identifier in ids}


def no_captured_reading(payload):
    # No stand-in can interpret structure: a Reading the captured run never
    # made means the replay no longer describes that run.
    raise AssertionError(f"No captured Reading for elements {[e['element_id'] for e in payload['elements']]}.")


class EquivalenceReplay(IdTranslatingReplay):
    KEYED = ("reading", "adjudication", "gap_probe", "extraction_correction", "gap_probe_correction")
    STAND_IN = {"reading": no_captured_reading, "gap_probe": nothing_found, "extraction_correction": no_more_corrections,
                "gap_probe_correction": no_more_claims}

    def __init__(self, path):
        super().__init__(path, by_stage=True)
        self.captured = {stage: [s for s in self.steps if s["stage"] == stage] for stage in self.KEYED}
        self.used = {stage: 0 for stage in self.KEYED}
        self.answers = {}
        for step in self.captured["adjudication"]:
            for answer in step["output"]["answers"]:
                self.answers.setdefault(answer["question_id"], answer)
        for stage in self.KEYED:
            self.queues[stage] = []
        # Work asked of a captured call that it never saw (a reshuffled pack).
        self.unaligned: list = []

    def generate_structured(self, *, system_prompt, user_payload, response_schema, config):
        stage = user_payload.get("stage")
        if stage in self.KEYED:
            self.queues[stage] = [self.select(stage, user_payload)]
        return super().generate_structured(system_prompt=system_prompt, user_payload=user_payload,
                                           response_schema=response_schema, config=config)

    def select(self, stage, payload) -> dict:
        work = _work(stage, payload)
        if stage == "adjudication":
            unanswered = [q for q in payload["questions"] if q["question_id"] not in self.answers]
            answers = [self.answers[q["question_id"]] for q in payload["questions"] if q["question_id"] in self.answers]
            if unanswered:
                answers += single_option_oracle({**payload, "questions": unanswered})["answers"]
            return {"answers": answers}

        wanted = _ids(work)
        steps = self.captured[stage]
        for position in range(self.used[stage], len(steps)):
            recorded = _ids(steps[position].get("request") or {})
            if recorded & wanted:
                self.used[stage] = position + 1
                if wanted - recorded:
                    self.unaligned.append({"stage": stage, "not_in_captured_call": sorted(map(list, wanted - recorded))})
                return self.restrict(stage, steps[position], work)
        return self.STAND_IN[stage](payload)

    @staticmethod
    def restrict(stage, step, work) -> dict:
        output = json.loads(json.dumps(step["output"]))
        if stage == "reading":
            asked = set(work["elements"])
            output["readings"] = [r for r in output["readings"] if r["element_id"] in asked]
            return output
        recorded_items = set((step.get("request") or {}).get("items", []))
        not_asked = recorded_items - set(work.get("items", []))
        graph = output.get("evidence") if stage == "extraction_correction" else output.get("claims")
        for kind, key in (("entities", "eid"), ("assertions", "aid"), ("facts", "fid")):
            if graph and graph.get(kind):
                graph[kind] = [item for item in graph[kind] if item[key] not in not_asked]
        if "verdicts" in output:
            asked = set(work.get("requirements", []))
            output["verdicts"] = [v for v in output["verdicts"] if v["requirement_id"] in asked]
        return output


class LateRoundFixture(InternationalFlyerFixture):
    """The model of live run bb3535b7, exactly as its catalogue was captured:
    a Stage belongs to one Tournament and needs a Match; a Match has exactly
    two Teams, a Venue and a Stage; a Venue hosts one Match; a Team plays in
    one Match and one Tournament; a Tournament has at least two Teams."""

    def setUp(self):
        self.model = self.make_model(
            name="International Rugby Tournament",
            purpose="Understand the structure of the tournament and how teams progress through the competition.",
            scope="Tournament structure, participating teams, competition stages, fixtures, matches, venues, results, and progression between stages.",
            exclusions="Players and rosters; contracts and finances; ticketing and commercial matters; detailed match statistics; broader rugby administration.",
        )
        types = {k: self.make_object_type(self.model, key=k) for k in ("match", "stage", "team", "tournament", "venue")}
        rel = {key: self.make_relationship_type(self.model, key=key, name=name) for key, name in (
            ("has_match", "has match"), ("has_stage", "has stage"), ("has_team", "has team"), ("has_team_2", "has team"), ("played_at", "played at"),
        )}
        self.make_rule(rel["has_match"], types["stage"], types["match"], object_minimum=1, subject_minimum=1)
        self.make_rule(rel["has_stage"], types["tournament"], types["stage"], object_minimum=1, subject_minimum=1, subject_maximum=1)
        self.make_rule(rel["has_team"], types["match"], types["team"], object_minimum=2, object_maximum=2, subject_minimum=1, subject_maximum=1)
        self.make_rule(rel["has_team_2"], types["tournament"], types["team"], object_minimum=2, subject_minimum=1, subject_maximum=1)
        self.make_rule(rel["played_at"], types["match"], types["venue"], object_minimum=1, subject_minimum=1, subject_maximum=1)
        self.assets = flyer_assets()
        self.bundle = EvidenceBundle.from_assets(self.assets)


HEADING = "PACIFIC INTERNATIONAL RUGBY CHAMPIONSHIP 2027"
# The teams probe round 2 extracted (accepted under these ids).
TEAM_EIDS = {"New Zealand": "E19", "Fiji": "E20", "Japan": "E21", "Samoa": "E22",
             "Australia": "E23", "Argentina": "E24", "South Africa": "E25", "Tonga": "E26"}


def late_round_correction(payload):
    """A correction of the live run's second probe round (one it never got):
    the tournament -> team claims citing the title heading their table sits
    under (support 'structural', as the anchors show), and the match -> team
    claims its verdicts named but never emitted."""

    assertions, verdicts, number = [], [], 32
    for entry in payload["invalid_claims"]:
        item = dict(entry["item"])
        item.update(support="structural", provenance=[{"source_id": "S1", "excerpt": HEADING, "segment_id": "S1#1", "locator": None},
                                                      *item["provenance"]])
        assertions.append(item)
    rows = [s["text"] for s in payload["segments"]]
    for invalid in payload["invalid_verdicts"]:
        requirement = invalid["requirement"]
        match = requirement["entity"]
        row = next(text for text in rows if match["name"] in text)
        claim_ids = []
        for team in match["name"].split(" v "):
            claim_ids.append(f"A{number}")
            assertions.append(assertion(f"A{number}", match["eid"], "has team", TEAM_EIDS[team], excerpt=row).model_dump(mode="json"))
            number += 1
        verdicts.append({"requirement_id": requirement["requirement_id"], "status": "found", "claim_ids": claim_ids})
    return {"claims": {"assertions": assertions}, "verdicts": verdicts}


class LateRoundRegressionTests(LateRoundFixture):
    """Live run bb3535b7 ended with an empty ChangeSet: its last probe round
    emitted fixable tournament -> team claims (a missing heading citation) and
    verdicts naming match -> team claims it never emitted, and the run's only
    probe correction had been spent by round 1. Replayed by stage through the
    corrected workflow; stand-ins answer the calls the live run never made."""

    LIVE_RULE_IDS = {
        "7e0f2bba-d669-4a8e-a731-28fedcbfd8ba": "has_stage",
        "828f6641-0dad-42cf-90b9-b0f24f9fefec": "has_match",
        "f4d78957-4874-4704-acca-4a915850da7b": "played_at",
        "802ae184-5eb8-4bd8-94c0-8d8622312641": "has_team_2",
        "39b8a3dc-039d-40cc-862e-581ccee85796": "has_team",
    }

    def test_the_bundle_is_the_live_one(self):
        captured = {"S1#1": HEADING, "S1#t1.r1": "Pool A | New Zealand | Fiji | Japan | Samoa",
                    "S1#t3.r1": "Pool A | New Zealand v Fiji | Eden Park",
                    "S1#t4.r2": "Quarter-final | Pool B winner v Pool A runner-up | Sky Stadium"}
        self.assertEqual({sid: self.bundle.segment(sid).text for sid in captured}, captured)

    def replay(self):
        rules = {r.relationship_type.key: str(r.id) for r in RelationshipTypeRule.objects.filter(relationship_type__model=self.model)}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for step in TRACE_LATE_ROUND.glob("*.json"):
            text = step.read_text(encoding="utf-8")
            for live, key in self.LIVE_RULE_IDS.items():
                text = text.replace(live, rules[key])
            (Path(directory.name) / step.name).write_text(text, encoding="utf-8")
        # The live run filed the tournament under a reused id (E12); here it
        # gets a fresh one, which later captured rounds are translated to.
        provider = IdTranslatingReplay(directory.name, inject={
            "extraction_correction": [no_more_corrections] * 2,
            "adjudication": [single_option_oracle] * 3,
            "gap_probe": [nothing_found] * 3,
            "gap_probe_correction": [late_round_correction, no_more_claims, no_more_claims],
        })
        return provider, self.run_reconcile(provider)

    def test_the_late_round_is_corrected_and_the_supported_part_is_proposed(self):
        provider, result = self.replay()

        # The second round gets its own correction, carrying both defects.
        corrections = [p for stage, p in zip(provider.requested, provider.payloads) if stage == "gap_probe_correction"]
        self.assertEqual(len(corrections), 2)
        late = corrections[1]
        self.assertEqual(sorted(e["id"] for e in late["invalid_claims"]), [f"A{n}" for n in range(23, 31)])
        self.assertEqual(sorted(v["requirement"]["entity"]["name"] for v in late["invalid_verdicts"]),
                         ["Australia v Argentina", "Japan v Samoa", "New Zealand v Fiji", "South Africa v Tonga"])
        self.assertEqual({v["issues"][0]["code"] for v in late["invalid_verdicts"]}, {"verdict_claim_missing"})
        # The dependency layer it recovered is processed, and what the evidence
        # supports reaches a Proposal instead of an empty ChangeSet.
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "partial")
        created = {c.after["name"] for c in ProposalChange.objects.filter(proposal_id=result.proposal_id)
                   if c.target_type == "Object" and c.operation == "create"}
        expected = {"Pacific International Rugby Championship", "Pool A", "Pool B", "New Zealand v Fiji", "Japan v Samoa",
                    "Australia v Argentina", "South Africa v Tonga", "Eden Park", "Sky Stadium", "Forsyth Barr Stadium",
                    "FMG Stadium Waikato", *TEAM_EIDS}
        self.assertTrue(expected <= created, expected - created)
        # What no claim supports stays blocked: knockout stages (no identified
        # teams), and venues with no identified match.
        unsupported = {"Quarter-finals", "Semi-finals", "Final", "McLean Park", "Orangetheory Stadium"}
        self.assertTrue(unsupported <= {b["target"] for b in result.blocked_targets}, result.blocked_targets)
        self.assertFalse(unsupported & created)
        self.assertLessEqual(result.provider_calls, settings.AI_WORKFLOW_MAX_PROVIDER_CALLS + settings.AI_TERMINAL_EXPLANATION_MAX_CALLS)


TOURNAMENT = "Pacific International Rugby Championship 2027"


class OpenTeamDecisionRegressionTests(LateRoundFixture):
    """Live run f3e0d659 ended with an empty ChangeSet. Its probes recovered
    every team, match and venue, but the tournament -> team claims kept
    omitting the title heading. Both corrections were shown that heading
    among the claim's `cited_segments` (its ancestors were mixed in), so the
    feedback contradicted itself. The claims arrived only in the last round;
    their mapping decision could not be adjudicated within budget, and the
    block report blamed an unrelated stage ("Semi-final has_match"), so
    Verification approved."""

    LIVE_RULE_IDS = LateRoundRegressionTests.LIVE_RULE_IDS

    # The live run's 14 calls, less its first Adjudication round, which asked
    # only indirect_classification questions (never asked now): the budget
    # that leaves the run's last decision open, as it was live.
    LIVE_BUDGET = 13

    def replay(self, budget=LIVE_BUDGET, **inject):
        rules = {r.relationship_type.key: str(r.id) for r in RelationshipTypeRule.objects.filter(relationship_type__model=self.model)}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for step in TRACE_OPEN_TEAMS.glob("*.json"):
            if no_longer_asked(step):
                continue
            text = step.read_text(encoding="utf-8")
            for live, key in self.LIVE_RULE_IDS.items():
                text = text.replace(live, rules[key])
            (Path(directory.name) / step.name).write_text(text, encoding="utf-8")
        provider = ReplayProvider(directory.name, inject=inject or None)
        with override_settings(AI_WORKFLOW_MAX_PROVIDER_CALLS=budget):
            return provider, self.run_reconcile(provider)

    def test_a_correction_sees_exactly_what_a_claim_cites(self):
        provider, _ = self.replay()

        correction = provider.payloads[provider.requested.index("gap_probe_correction")]
        a11 = next(e for e in correction["invalid_claims"] if e["id"] == "A11")
        self.assertEqual([s["segment_id"] for s in a11["cited_segments"]], ["S1#5", "S1#t1.r1"])
        # The title heading it must add is context -- citable, not cited.
        self.assertEqual([s["segment_id"] for s in a11["context_segments"]], ["S1#1", "S1#t1"])

    def test_a_block_held_by_an_open_decision_names_that_decision(self):
        provider, result = self.replay()

        self.assertEqual(provider.requested[-1], "verification")
        open_decisions = provider.payloads[-1]["open_decisions"]
        self.assertEqual([d["question_id"] for d in open_decisions], ["predicate_mapping:has_team:tournament:team"])
        for venue in ("Eden Park", "Forsyth Barr Stadium", "FMG Stadium Waikato"):
            blocked = next(b for b in result.blocked_targets if b["target"] == venue)
            cause = blocked["cascade"]["cause"]
            # The open tournament <-> team decision, from whichever side the
            # chain reaches first (a team needs its tournament, too).
            self.assertEqual(cause["relationship_type_key"], "has_team_2", blocked["cascade"])
            self.assertIn(cause["entity"], {TOURNAMENT, *TEAM_EIDS})
            self.assertTrue(cause["pending_decision"])
        message = next(f.message for f in result.findings if "'Eden Park'" in f.message and f.message.startswith("Not included"))
        self.assertIn("undecided", message)
        self.assertNotIn("Semi-final", message)

    def test_that_open_decision_was_the_only_thing_blocking_the_supported_part(self):
        # Test-only counterfactual: one more call answers the open decision.
        _, result = self.replay(budget=self.LIVE_BUDGET + 1, adjudication=[single_option_oracle], gap_probe=[nothing_found] * 2,
                                gap_probe_correction=[no_more_claims] * 2)

        created = {c.after["name"] for c in ProposalChange.objects.filter(proposal_id=result.proposal_id)
                   if c.target_type == "Object" and c.operation == "create"}
        expected = {TOURNAMENT, "Pool Stage", "New Zealand v Fiji", "Japan v Samoa", "Australia v Argentina", "South Africa v Tonga",
                    "Eden Park", "Sky Stadium", "Forsyth Barr Stadium", "FMG Stadium Waikato", *TEAM_EIDS}
        self.assertTrue(expected <= created, expected - created)
        unsupported = {"Quarter-final", "Semi-final", "Final", "McLean Park", "Orangetheory Stadium"}
        self.assertFalse(unsupported & created)


class EmptyFoundRegressionTests(LateRoundFixture):
    """Live run 7f0fcac7: probe round 1 answered "found" for 13 of 20
    requirements while naming no assertion (nothing, or only entities). That
    was accepted as a verdict, re-probed a round later with feedback that
    implied invalid claims existed ("citing no claim, but those claims do not
    relate ..."), and flipped to not_stated -- a confirmed absence. An empty
    "found" now breaks the verdict contract: it is re-asked in the same
    round's correction, and never becomes a coverage result."""

    LIVE_RULE_IDS = LateRoundRegressionTests.LIVE_RULE_IDS

    def replay(self):
        rules = {r.relationship_type.key: str(r.id) for r in RelationshipTypeRule.objects.filter(relationship_type__model=self.model)}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for step in TRACE_EMPTY_FOUND.glob("*.json"):
            text = step.read_text(encoding="utf-8")
            for live, key in self.LIVE_RULE_IDS.items():
                text = text.replace(live, rules[key])
            (Path(directory.name) / step.name).write_text(text, encoding="utf-8")
        # Keyed by the work asked for: the live run's first correction re-asked
        # only unanchored claims no segment could anchor, which are no longer
        # re-asked -- its output must not answer the segment re-ask that comes
        # first now.
        provider = EquivalenceReplay(directory.name)
        round_one = next(s for s in load(directory.name) if s["stage"] == "gap_probe")["output"]
        return provider, self.run_reconcile(provider), round_one

    def test_empty_found_verdicts_are_re_asked_in_the_same_round(self):
        provider, _, round_one = self.replay()

        emitted_assertions = {a["aid"] for a in round_one["claims"]["assertions"]}
        empty = {v["requirement_id"] for v in round_one["verdicts"]
                 if v["status"] == "found" and not set(v["claim_ids"]) & emitted_assertions}
        self.assertEqual(len(empty), 14)  # 13 naming nothing or only entities, + Quarter-finals naming two shown entities

        first = provider.requested.index("gap_probe")
        self.assertEqual(provider.requested[first + 1], "gap_probe_correction")
        correction = provider.payloads[first + 1]
        self.assertEqual({v["requirement"]["requirement_id"] for v in correction["invalid_verdicts"]}, empty)
        self.assertEqual({v["issues"][0]["code"] for v in correction["invalid_verdicts"]}, {"verdict_without_claims"})
        eden = next(v for v in correction["invalid_verdicts"] if v["requirement"]["entity"].get("name") == "Eden Park")
        self.assertIn("nothing was emitted", eden["issues"][0]["message"])
        self.assertIn("not_stated", eden["issues"][0]["message"])
        pool_a = next(v for v in correction["invalid_verdicts"]
                      if v["requirement"]["entity"].get("name") == "Pool A" and v["previous_verdict"]["claim_ids"])
        self.assertIn("names only", pool_a["issues"][0]["message"])

    def test_an_uncorrected_empty_found_is_never_a_coverage_result(self):
        provider, _, _ = self.replay()

        eden = next(r for r in provider.payloads[provider.requested.index("gap_probe")]["requirements"]
                    if r.get("entity", {}).get("name") == "Eden Park")["requirement_id"]
        # Still empty after the round's correction: unsupported -- never "found"
        # and never a confirmed absence -- so it earns its one re-probe, told
        # that nothing was emitted.
        again = next(r for r in provider.payloads[[i for i, s in enumerate(provider.requested) if s == "gap_probe"][1]]["requirements"]
                     if r["requirement_id"] == eden)
        self.assertIn("emitted no claim", again["previous_answer"])
        self.assertNotIn("those claims", again["previous_answer"])


def _provenance(segments, *segment_ids):
    return [{"source_id": "S1", "segment_id": sid, "excerpt": segments[sid], "locator": None} for sid in segment_ids]


def fixture_reprobe(payload):
    """A test-only stand-in for the re-probes run 24063e61 never got: what
    the contested segments state -- each pool fixture row as a match with
    its two teams, its stage and its venue, and each team of the title's
    team table as the tournament's -- and a verdict for every requirement
    asked (found where an emitted assertion relates the entity to the kind
    looked for, otherwise not_stated)."""

    segments = {s["segment_id"]: s["text"] for s in payload["segments"]}
    already = payload.get("already_extracted") or {}
    shown = {e["name"]: e["eid"] for e in already.get("entities", [])}
    known = {(a["subject_eid"], a["predicate"], a["object_eid"]) for a in already.get("assertions", [])}
    kinds = {}  # eid -> the kind it is, for the verdicts
    entities, assertions = [], []
    number = iter(range(900, 1000))

    def relate(subject, predicate, obj, provenance, support="explicit"):
        if (subject, predicate, obj) not in known:
            assertions.append({"aid": f"A{next(number)}", "subject_eid": subject, "predicate": predicate, "object_eid": obj,
                               "support": support, "provenance": provenance})

    for sid in sorted(s for s in segments if s.startswith("S1#t3.r")):
        stage, label, ground = [c.strip() for c in segments[sid].split("|")]
        teams = label.split(" v ")
        if not all(name in shown for name in (stage, ground, *teams)):
            continue
        eid = shown.get(label)
        if eid is None:
            eid = f"E{next(number)}"
            entities.append({"eid": eid, "name": label, "type_label": "Match", "provenance": _provenance(segments, sid)})
        kinds.update({eid: "Match", shown[stage]: "Stage", shown[ground]: "Venue", **{shown[t]: "Team" for t in teams}})
        for team in teams:
            relate(eid, "has team", shown[team], _provenance(segments, sid))
        relate(shown[stage], "has match", eid, _provenance(segments, sid))
        relate(eid, "played at", shown[ground], _provenance(segments, sid))
    if HEADING in shown and "S1#1" in segments:
        kinds[shown[HEADING]] = "Tournament"
        for sid in sorted(s for s in segments if s.startswith("S1#t1.r")):
            for team in [c.strip() for c in segments[sid].split("|")][1:]:
                if team in shown:
                    kinds[shown[team]] = "Team"
                    relate(shown[HEADING], "has team", shown[team], _provenance(segments, "S1#1", sid), support="structural")

    asked = [*payload.get("requirements", []), *payload.get("missing_verdicts", []),
             *[v["requirement"] for v in payload.get("invalid_verdicts", [])]]
    verdicts = []
    for requirement in asked:
        eid = (requirement.get("entity") or {}).get("eid")
        wanted = requirement["looking_for"].get("kind")
        stating = [a["aid"] for a in assertions
                   if (a["subject_eid"] == eid and kinds.get(a["object_eid"]) == wanted)
                   or (a["object_eid"] == eid and kinds.get(a["subject_eid"]) == wanted)]
        verdicts.append({"requirement_id": requirement["requirement_id"], "status": "found" if stating else "not_stated",
                         "claim_ids": stating})
    return {"claims": {"entities": entities, "assertions": assertions}, "verdicts": verdicts}


TRACE_CONTESTED = Path(__file__).parent / "fixtures" / "traces" / "international_flyer_24063e61"


class ContestedAbsenceRegressionTests(LateRoundFixture):
    """Live run 24063e61 ended with every venue and stage blocked and an empty
    ChangeSet, approved. Its first probe round answered not_stated for every
    venue -> match and pool -> match requirement although each one's own
    segments held a fixture row under a 'Stage | Match | Venue' header, and
    its second answered not_stated for tournament -> team over the 'Teams'
    section under the title. Each was accepted as complete coverage. A
    not_stated its own pack's layout contradicts is now contested: re-probed
    once, told which segment and which header or heading."""

    LIVE_RULE_IDS = LateRoundRegressionTests.LIVE_RULE_IDS

    def replay(self, gap_probe=(), gap_probe_correction=()):
        rules = {r.relationship_type.key: str(r.id) for r in RelationshipTypeRule.objects.filter(relationship_type__model=self.model)}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for step in TRACE_CONTESTED.glob("*.json"):
            text = step.read_text(encoding="utf-8")
            for live, key in self.LIVE_RULE_IDS.items():
                text = text.replace(live, rules[key])
            (Path(directory.name) / step.name).write_text(text, encoding="utf-8")
        provider = ReplayProvider(directory.name, inject={
            "extraction_correction": [no_more_corrections] * 2,
            "adjudication": [single_option_oracle] * 4,
            "gap_probe": [*gap_probe, *[nothing_found] * 4],
            "gap_probe_correction": [*gap_probe_correction, *[no_more_claims] * 4],
            "verification": [approve().model_dump(mode="json")] * 2,
        })
        return provider, self.run_reconcile(provider)

    def probe_rounds(self, provider):
        return [p for stage, p in zip(provider.requested, provider.payloads) if stage == "gap_probe"]

    def names(self, payload, contested_only=False):
        return {r["entity"]["name"] for r in payload["requirements"] if r.get("entity")
                and (not contested_only or "said not_stated" in r.get("previous_answer", ""))}

    def test_absences_the_layout_contradicts_are_re_probed_once_with_their_layout(self):
        provider, _ = self.replay()

        rounds = self.probe_rounds(provider)
        # Round 1 is the live one; round 2 re-asks what its layout contests.
        self.assertEqual(self.names(rounds[1], contested_only=True),
                         {"Eden Park", "Sky Stadium", "Forsyth Barr Stadium", "FMG Stadium Waikato", "Pool A", "Pool B",
                          "Orangetheory Stadium"})
        # No header or section associates these with a match: their absence stands.
        for name in ("McLean Park", "Semi-finals", "Final"):
            self.assertNotIn(name, self.names(rounds[1]))
        eden = next(r for r in rounds[1]["requirements"] if r.get("entity", {}).get("name") == "Eden Park")
        self.assertIn("S1#t3.r1 is a row under the header 'Stage | Match | Venue'", eden["previous_answer"])
        self.assertIn("its 'Match' cell reads 'New Zealand v Fiji'", eden["previous_answer"])
        # The tournament -> team absence (round 2's own answer) is contested in round 3.
        tournament = next(r for r in rounds[2]["requirements"] if r.get("entity", {}).get("name") == HEADING)
        self.assertEqual(tournament["looking_for"]["kind"], "Team")
        self.assertIn("is an item in the section 'Teams' under the heading '" + HEADING + "'", tournament["previous_answer"])
        # Once: a second not_stated stands.
        later = [r["requirement_id"] for p in rounds[3:] for r in p["requirements"]]
        self.assertFalse({r["requirement_id"] for p in rounds[1:3] for r in p["requirements"] if "previous_answer" in r} & set(later))

    def test_what_the_contested_segments_state_reaches_a_partial_proposal(self):
        provider, result = self.replay(gap_probe=[fixture_reprobe] * 2, gap_probe_correction=[fixture_reprobe] * 2)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "partial")
        created = {normalize_name(c.after["name"]) for c in ProposalChange.objects.filter(proposal_id=result.proposal_id)
                   if c.target_type == "Object" and c.operation == "create"}
        expected = {HEADING, "Pool A", "Pool B", "New Zealand v Fiji", "Japan v Samoa", "Australia v Argentina", "South Africa v Tonga",
                    "Eden Park", "Sky Stadium", "Forsyth Barr Stadium", "FMG Stadium Waikato", *TEAM_EIDS}
        expected = {normalize_name(n) for n in expected}
        self.assertTrue(expected <= created, expected - created)
        unsupported = {"Quarter-finals", "Semi-finals", "Final", "McLean Park", "Orangetheory Stadium"}
        self.assertTrue(unsupported <= {b["target"] for b in result.blocked_targets}, result.blocked_targets)
        self.assertFalse({normalize_name(n) for n in unsupported} & created)
        self.assertLessEqual(result.provider_calls, settings.AI_WORKFLOW_MAX_PROVIDER_CALLS + settings.AI_TERMINAL_EXPLANATION_MAX_CALLS)


class VerdictContractUnitTests(SimpleTestCase):

    def found(self, *claim_ids, requirement_id="req:E7:rule:object"):
        return verdict(requirement_id, "found", claim_ids=list(claim_ids))

    def check(self, found, *, emitted=(), shown=(), needs_assertion=True, assertions=()):
        from ai.services.stages.gap_probe import verdict_issue

        return verdict_issue(found, set(emitted), set(shown), needs_assertion=needs_assertion, is_assertion=lambda c: c in assertions)

    def test_a_found_naming_nothing_is_a_contract_break(self):
        broken = self.check(self.found())

        self.assertEqual(broken.code, "verdict_without_claims")
        self.assertIn("nothing was emitted", broken.message)
        self.assertIn("not_stated", broken.message)

    def test_a_found_naming_only_entities_does_not_state_a_relationship(self):
        broken = self.check(self.found("E23", "E24"), emitted={"E23", "E24"})

        self.assertEqual(broken.code, "verdict_without_claims")
        self.assertIn("names only E23, E24", broken.message)

    def test_a_found_naming_an_assertion_is_a_verdict(self):
        self.assertIsNone(self.check(self.found("A1"), emitted={"A1"}, assertions={"A1"}))
        self.assertIsNone(self.check(self.found("a7"), shown={"a7"}, assertions={"a7"}))

    def test_a_target_found_may_name_an_entity(self):
        self.assertIsNone(self.check(self.found("E3", requirement_id="target:T1"), emitted={"E3"}, needs_assertion=False))
        self.assertEqual(self.check(self.found(requirement_id="target:T1"), needs_assertion=False).code, "verdict_without_claims")

    def test_naming_claims_never_given_is_still_its_own_break(self):
        self.assertEqual(self.check(self.found("Z1")).code, "verdict_claim_missing")

    def test_not_stated_is_not_checked(self):
        from ai.services.stages.gap_probe import verdict_issue

        self.assertIsNone(verdict_issue(verdict("req:E7:rule:object", "not_stated"), set(), set(), needs_assertion=True))


class FollowUpWordingTests(SimpleTestCase):

    REQUIREMENT = {"entity": {"eid": "E7", "name": "Alpha"}, "looking_for": {"kind": "Widget"}}

    def test_an_earlier_found_that_emitted_nothing_is_told_so(self):
        from ai.services.stages.gap_probe import previous_answer

        text = previous_answer(self.REQUIREMENT, [])

        self.assertIn("emitted no claim", text)
        self.assertIn("not_stated", text)
        self.assertIn("'Alpha'", text)
        # Never as if claims had existed.
        self.assertNotIn("citing", text)
        self.assertNotIn("those claims", text)

    def test_an_earlier_found_citing_claims_that_did_not_count_names_them(self):
        from ai.services.stages.gap_probe import previous_answer

        text = previous_answer(self.REQUIREMENT, ["A12"])

        self.assertIn("citing A12, but those claims do not relate 'Alpha' to any Widget", text)
        self.assertNotIn("emitted no claim", text)

    def test_a_target_gap_follow_up(self):
        from ai.services.stages.gap_probe import previous_answer

        self.assertIn("emitted no claim", previous_answer({"looking_for": {"kind": "Widget"}}, []))
        self.assertIn("none of those claims is a Widget", previous_answer({"looking_for": {"kind": "Widget"}}, ["E3"]))

    def test_a_contested_absence_names_its_layout(self):
        from ai.services.stages.gap_probe import previous_answer

        text = previous_answer(self.REQUIREMENT, [], [
            {"segment_id": "S1#t2.r1", "header": "Region | Widget | Depot", "column": "Widget", "cell": "Gamma v Delta"},
            {"segment_id": "S1#9", "heading": "Widgets", "under": "Alpha"},
        ])

        self.assertIn("An earlier answer said not_stated", text)
        self.assertIn("S1#t2.r1 is a row under the header 'Region | Widget | Depot'", text)
        self.assertIn("its 'Widget' cell reads 'Gamma v Delta'", text)
        self.assertIn("S1#9 is an item in the section 'Widgets' under the heading 'Alpha'", text)
        self.assertIn("answer not_stated only if they do not state it", text)
        self.assertNotIn("emitted no claim", text)
        lowered = text.lower()
        self.assertFalse([w for w in DOMAIN_WORDS if w in lowered], text)


class LabelledEvidenceUnitTests(SimpleTestCase):
    """What contests a `not_stated`: layout associating the entity with the
    counterpart's kind -- never the kind's word in a row's own text, nor two
    names merely appearing together."""

    BLOCKS = [
        {"kind": "heading", "level": 1, "text": "Acme Network"},
        {"kind": "heading", "level": 2, "text": "Depots"},
        {"kind": "table", "header": ["Depot", "City", "Primary use"], "rows": [["North Depot", "Leeds", "Order dispatch"]]},
        {"kind": "heading", "level": 2, "text": "Order schedule"},
        {"kind": "table", "header": ["Region", "Order", "Depot"],
         "rows": [["East", "Acme v Bolt", "North Depot"], ["West", "Crate v Dune", "Old North Depot Annex"]]},
        {"kind": "heading", "level": 2, "text": "Orders"},
        {"kind": "list_item", "text": "Crate v Dune"},
        {"kind": "paragraph", "text": "North Depot handles every order."},
    ]

    def setUp(self):
        self.bundle = EvidenceBundle.from_assets([{"name": "network", "content": "", "blocks": self.BLOCKS}])
        self.ids = {s.text: s.segment_id for s in self.bundle.segments()}

    def labelled(self, names, kind="Order"):
        from ai.services.reconcile.near_miss import labelled_evidence

        segments = [s for s in self.bundle.segments() if s.kind in ("table_row", "list_item", "text_block")]
        return {e["segment_id"]: e for e in labelled_evidence(self.bundle, segments, names, [kind])}

    def test_a_row_under_a_header_naming_the_kind_counts(self):
        found = self.labelled(["North Depot"])

        row = self.ids["East | Acme v Bolt | North Depot"]
        self.assertEqual(found[row], {"segment_id": row, "header": "Region | Order | Depot", "column": "Order", "cell": "Acme v Bolt"})

    def test_an_item_in_a_section_headed_by_the_kind_under_the_entity_counts(self):
        found = self.labelled(["Acme Network"])

        item = self.ids["Crate v Dune"]
        self.assertEqual(found[item], {"segment_id": item, "heading": "Orders", "under": "Acme Network"})

    def test_the_kind_only_in_a_rows_own_text_does_not_count(self):
        self.assertNotIn(self.ids["North Depot | Leeds | Order dispatch"], self.labelled(["North Depot"]))

    def test_names_merely_appearing_together_do_not_count(self):
        found = self.labelled(["North Depot"])

        # The entity inside a larger cell is not that cell.
        self.assertNotIn(self.ids["West | Crate v Dune | Old North Depot Annex"], found)
        # A sentence naming both, with no heading naming the entity above it.
        self.assertNotIn(self.ids["North Depot handles every order."], found)
        self.assertEqual(list(found), [self.ids["East | Acme v Bolt | North Depot"]])


# Words of the flyer domain this suite runs on: none may be injected by the
# engine's own (domain-agnostic) feedback.
DOMAIN_WORDS = ("match", "fixture", "team", "venue", "stage", "pool", "rugby", "tournament", "player")


class DomainNeutralWordingTests(SimpleTestCase):

    def assertNeutral(self, text):
        lowered = text.lower()
        self.assertFalse([w for w in DOMAIN_WORDS if w in lowered], text)

    def test_the_self_reference_message(self):
        from ai.services.evidence_bundle import EvidenceBundle
        from ai.services.evidence_graph import validate_evidence_graph

        bundle = EvidenceBundle.from_assets([{"name": "doc.txt", "content": "Alpha links to Beta."}])
        found = validate_evidence_graph(graph(entity("E1", "Alpha", "thing", excerpt="Alpha"),
                                              assertion("A1", "E1", "links to Beta", "E1", excerpt="Alpha links to Beta.")),
                                        bundle=bundle, intent_text="")
        [message] = [i.message for i in found if i.code == "self_reference"]
        self.assertNeutral(message)
        self.assertIn("withdraw the claim", message)
        self.assertIn("under the name the source uses", message)

    def test_the_coverage_re_ask(self):
        from ai.services.stages.extraction import unaccounted_reask

        for names in (["Alpha"], ["Alpha", "Beta"]):
            text = unaccounted_reask(names)
            self.assertNeutral(text)
            self.assertIn("'Alpha'", text)

    def test_the_target_gap_question(self):
        from types import SimpleNamespace

        from ai.services.reconcile.analysis import TargetGap
        from ai.services.reconcile.near_miss import target_question

        index = SimpleNamespace(type_by_id=lambda type_id: SimpleNamespace(name="Widget"))
        gap = TargetGap("target:T1", "T1", "object_type", "t", "widgets", "add", "uncovered", ["S1#1"], ["Alpha"])
        text = target_question(gap, index)
        self.assertNeutral(text)
        self.assertIn("'Alpha'", text)

    def test_the_verdict_contract_and_follow_up(self):
        from ai.services.stages.gap_probe import previous_answer, verdict_issue

        self.assertNeutral(verdict_issue(verdict("req:E1:r:object", "found"), set(), set(), needs_assertion=True).message)
        self.assertNeutral(previous_answer({"entity": {"name": "Alpha"}, "looking_for": {"kind": "Widget"}}, []))


# -- prompt contracts ------------------------------------------------------------------


# Words of the domains the live tests use. "stage" is also an engine word
# ("STAGE: EXTRACTION", "one stage of OnyxJar's ... workflow"), so it is
# checked outside those phrases.
PROMPT_DOMAIN_WORDS = ("match", "fixture", "team", "venue", "pool", "rugby", "tournament", "player", "championship",
                       "eden park", "fiji", "zealand", "lions", "acme", "supplier", "league")


def reconcile_prompts():
    from ai.services.operation_definitions import RECONCILE
    from ai.services.stages import prompts

    return {
        "preamble": prompts.preamble(RECONCILE),
        "CLAIM_CONTRACT": prompts.CLAIM_CONTRACT,
        "EXTRACTION": prompts.EXTRACTION,
        "EXTRACTION_CORRECTION": prompts.EXTRACTION_CORRECTION,
        "ADJUDICATION": prompts.ADJUDICATION,
        "GAP_PROBE": prompts.GAP_PROBE,
        "GAP_PROBE_CORRECTION": prompts.GAP_PROBE_CORRECTION,
        "VERIFICATION": prompts.VERIFICATION,
    }


def domain_terms(text) -> list[str]:
    lowered = text.lower()
    found = [w for w in PROMPT_DOMAIN_WORDS if re.search(rf"\b{re.escape(w)}", lowered)]
    if re.search(r"\bstages?\b", re.sub(r"stage: [a-z ]+\.|one stage of onyxjar", "", lowered)):
        found.append("stage")
    return found


class ReconcilePromptContractTests(SimpleTestCase):
    """Every RECONCILE system prompt is domain-agnostic and states the
    contracts the code enforces on its output."""

    def test_no_prompt_carries_domain_vocabulary(self):
        for name, text in reconcile_prompts().items():
            with self.subTest(prompt=name):
                self.assertEqual(domain_terms(text), [], text)

    def test_the_claim_contract_travels_with_every_stage_that_makes_claims(self):
        from ai.services.stages import prompts

        # The probe and the reviewer never see the Extraction prompt: each
        # carries the contract its claims are checked against.
        for name in ("EXTRACTION", "GAP_PROBE", "VERIFICATION"):
            with self.subTest(prompt=name):
                self.assertIn(prompts.CLAIM_CONTRACT, getattr(prompts, name))
        self.assertNotIn("exactly as Extraction does", prompts.GAP_PROBE)

    def test_the_claim_contract_states_what_validation_enforces(self):
        from ai.services.evidence_graph import EvidenceAssertion, EvidenceEntity
        from ai.services.stages.prompts import CLAIM_CONTRACT

        for support in get_args(EvidenceAssertion.model_fields["support"].annotation):
            self.assertIn(f"'{support}'", CLAIM_CONTRACT)
        for specificity in get_args(EvidenceEntity.model_fields["specificity"].annotation):
            if specificity != "specific":
                self.assertIn(f"specificity='{specificity}'", CLAIM_CONTRACT)
        for rule in ("Never make up a name", "Never relate an entity to itself", "one assertion per member",
                     "cites nothing -- to rely on a heading, cite the heading itself", "rejects a claim"):
            self.assertIn(rule, CLAIM_CONTRACT)

    def test_the_probe_states_the_found_contract_for_both_requirement_kinds(self):
        from ai.services.reconcile.responses import ProbeVerdict
        from ai.services.stages.prompts import GAP_PROBE

        for status in get_args(ProbeVerdict.model_fields["status"].annotation):
            self.assertIn(f"'{status}'", GAP_PROBE)
        self.assertIn("ENTITY requirement (it has `entity`)", GAP_PROBE)
        self.assertIn("TARGET requirement (it has `requested`", GAP_PROBE)
        self.assertIn("an entity alone states no relationship", GAP_PROBE)
        self.assertIn("A 'found' with no such claim is invalid", GAP_PROBE)
        self.assertIn("`previous_answer`", GAP_PROBE)

    def test_corrections_separate_cited_from_context_and_reserve_ids(self):
        from ai.services.stages.prompts import EXTRACTION_CORRECTION, GAP_PROBE_CORRECTION

        for name, text in (("extraction", EXTRACTION_CORRECTION), ("gap_probe", GAP_PROBE_CORRECTION)):
            with self.subTest(correction=name):
                self.assertIn("`cited_segments`, exactly", text)
                self.assertIn("NOT cited", text)
                self.assertIn("is used ONLY for its corrected version", text)
                self.assertIn("withdraw", text)
        self.assertIn("naming no claim that states it (nothing was emitted for it)", GAP_PROBE_CORRECTION)

    def test_verification_states_how_objections_are_acted_on(self):
        from ai.services.reconcile.responses import Objection
        from ai.services.stages.prompts import VERIFICATION

        for kind in get_args(Objection.model_fields["kind"].annotation):
            self.assertIn(kind, VERIFICATION)
        self.assertIn("Only 'material' objections are acted on", VERIFICATION)
        self.assertIn("decision 'esc:..'", VERIFICATION)
        self.assertIn("by their eid", VERIFICATION)

    def test_the_structural_example_is_abstract_and_relates_two_different_entities(self):
        from ai.services.stages.prompts import CLAIM_CONTRACT

        # Run 3f801647 copied a literal example predicate ("is listed under")
        # into claims relating a row to its own name.
        for name, text in reconcile_prompts().items():
            with self.subTest(prompt=name):
                self.assertNotIn("is listed under", text)
                # A predicate is only ever shown as a placeholder, never as text to reuse.
                self.assertEqual(re.findall(r"predicate:'(?!<)", text), [])
        self.assertIn("subject_eid:'<", CLAIM_CONTRACT)
        self.assertIn("object_eid:'<", CLAIM_CONTRACT)
        self.assertIn("never text to reuse", CLAIM_CONTRACT)
        self.assertIn("always relates two different entities", CLAIM_CONTRACT)
        self.assertIn("Never relate an entity to itself, to its own name, or to its own table or header", CLAIM_CONTRACT)

    def test_composite_expressions_name_their_entities_but_co_occurrence_is_no_relationship(self):
        from ai.services.stages.prompts import CLAIM_CONTRACT

        self.assertIn("explicitly identify named entities and express a relationship between them", CLAIM_CONTRACT)
        self.assertIn("'Entity A v Entity B'", CLAIM_CONTRACT)
        self.assertIn("'Entity C | Entity A | Entity B' under a header that defines each column", CLAIM_CONTRACT)
        self.assertIn("extract each of them, and record the relationship the label or row actually states", CLAIM_CONTRACT)
        self.assertIn("Names that merely appear together", CLAIM_CONTRACT)
        self.assertIn("are not a relationship", CLAIM_CONTRACT)

    def test_implied_means_general_knowledge_only(self):
        from ai.services.stages.prompts import CLAIM_CONTRACT

        self.assertIn("its own words, the names it contains, and what its layout conveys", CLAIM_CONTRACT)
        self.assertIn("These are statements, not implications", CLAIM_CONTRACT)
        self.assertIn("inferred only from general knowledge, convention, plausibility or what would normally be true",
                      CLAIM_CONTRACT)
        self.assertNotIn("merely plausible, typical or implied", CLAIM_CONTRACT)

    def test_adjudication_states_which_answers_need_citations(self):
        from ai.services.stages.prompts import ADJUDICATION

        self.assertIn("Every answer except 'undecidable' must cite", ADJUDICATION)
        self.assertIn("not on what is plausible", ADJUDICATION)


class EngineMessageWordingTests(SimpleTestCase):
    """Text the engine generates for a model: built from the input's own
    names, never a domain example, and stating the found contract."""

    def test_the_requirement_question_states_the_found_contract(self):
        from ai.services.reconcile.near_miss import question

        index = SimpleNamespace(object_types={"t": SimpleNamespace(name="Widget")},
                                relationship_types={"r": SimpleNamespace(name="is part of")})
        analysis = SimpleNamespace(cluster_name=lambda cid: "Alpha")
        requirement = SimpleNamespace(counterpart_type_id="t", relationship_type_id="r", cluster_id="c")
        text = question(requirement, analysis, index)

        self.assertEqual(domain_terms(text), [])
        self.assertIn("emit the assertion relating 'Alpha'", text)
        self.assertIn("claim_ids", text)
        self.assertIn("not_stated", text)

    def test_the_target_question_states_the_found_contract(self):
        from ai.services.reconcile.analysis import TargetGap
        from ai.services.reconcile.near_miss import target_question

        index = SimpleNamespace(type_by_id=lambda type_id: SimpleNamespace(name="Widget"))
        for gap in (TargetGap("target:T1", "T1", "object_type", "t", "widgets", "add", "none_evidenced", ["S1#1"]),
                    TargetGap("target:T1", "T1", "object_type", "t", "widgets", "add", "uncovered", ["S1#1"], ["Alpha"])):
            text = target_question(gap, index)
            self.assertEqual(domain_terms(text), [])
            self.assertIn("name them in claim_ids", text)

    def test_grounding_and_frame_messages_are_neutral(self):
        from ai.services.evidence_bundle import EvidenceBundle
        from ai.services.grounding import grounding_issues
        from ai.services.intent_frame import validate_intent_frame

        bundle = EvidenceBundle.from_assets([{"name": "doc.txt", "content": "Alpha is here.\n\nBeta is there."}])
        unanchored = grounding_issues(graph(entity("E1", "Alpha", "thing", excerpt="Alpha is here."),
                                            entity("E2", "Beta", "thing", excerpt="Beta is there."),
                                            assertion("A1", "E1", "is linked to", "E2", excerpt="Alpha is here.")), bundle=bundle)
        [message] = [i.message for i in unanchored if i.item_id == "A1"]
        self.assertEqual(domain_terms(message), [])
        self.assertIn("each by its own segment_id", message)

        framed = frame([target("T1", "widgets", "add the widgets ... now")])
        messages = [i.message for i in validate_intent_frame(framed, "Please add the widgets to the model now.")]
        self.assertTrue(messages)
        for message in messages:
            self.assertEqual(domain_terms(message), [], message)


class NoTeamsRegressionTests(LateRoundFixture):
    """Live run 3f801647 (after the prompt cleanup): every contract held --
    empty "found" verdicts were re-asked in their round, bad citations were
    rejected, block causes were accurate -- but no team was ever extracted, so
    every match failed its teams and every venue and stage was blocked. Kept
    so the next live run can be measured against this exact failure."""

    LIVE_RULE_IDS = LateRoundRegressionTests.LIVE_RULE_IDS

    def replay(self):
        rules = {r.relationship_type.key: str(r.id) for r in RelationshipTypeRule.objects.filter(relationship_type__model=self.model)}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for step in TRACE_NO_TEAMS.glob("*.json"):
            text = step.read_text(encoding="utf-8")
            for live, key in self.LIVE_RULE_IDS.items():
                text = text.replace(live, rules[key])
            (Path(directory.name) / step.name).write_text(text, encoding="utf-8")
        provider = ReplayProvider(directory.name, inject={
            "extraction_correction": [no_more_corrections] * 2,
            "adjudication": [single_option_oracle] * 4,
            "gap_probe": [nothing_found] * 3,
            "gap_probe_correction": [no_more_claims] * 4,
        })
        return provider, self.run_reconcile(provider)

    def test_the_empty_found_verdicts_were_re_asked_in_their_round(self):
        provider, _ = self.replay()

        first = provider.requested.index("gap_probe")
        self.assertEqual(provider.requested[first + 1], "gap_probe_correction")
        correction = provider.payloads[first + 1]
        by_code = {}
        for invalid in correction["invalid_verdicts"]:
            by_code.setdefault(invalid["issues"][0]["code"], set()).add(invalid["requirement"]["entity"]["name"])
        self.assertEqual(by_code["verdict_without_claims"], {"Sky Stadium", "Forsyth Barr Stadium", "FMG Stadium Waikato"})
        # The live run filed "Final is played at Eden Park" under a reused id
        # (A2); here that claim has a fresh id, so the captured verdict citing
        # A2 names a claim this run never emitted -- re-asked, never trusted.
        self.assertEqual(by_code.get("verdict_claim_missing"), {"Eden Park"})

    def test_without_teams_every_venue_is_blocked_by_its_matches_teams(self):
        provider, result = self.replay()

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertFalse(ProposalChange.objects.filter(proposal_id=result.proposal_id).exists())
        verification = provider.payloads[provider.requested.index("verification")]
        self.assertEqual(verification["open_decisions"], [])
        blocked = {b["target"]: b for b in result.blocked_targets}
        for venue, match in (("Eden Park", "New Zealand v Fiji"), ("Sky Stadium", "Japan v Samoa"),
                             ("Forsyth Barr Stadium", "Australia v Argentina"), ("FMG Stadium Waikato", "South Africa v Tonga")):
            cause = blocked[venue]["cascade"]["cause"]
            self.assertEqual((cause["entity"], cause["relationship_type_key"], cause["evidenced"]), (match, "has_team", 0))


class ReusedIdRegressionTests(LateRoundFixture):
    """Live run 286357bd: the six self-referencing claims A1-A6 were re-asked
    in the first correction and withdrawn; the next correction's six new
    match -> stage claims ("is in stage", each citing its fixture row with a
    misplaced excerpt) were filed under the same ids, inherited "already
    re-asked", and were dropped without their own correction. Ingress no
    longer reuses an id with a history."""

    LIVE_RULE_IDS = LateRoundRegressionTests.LIVE_RULE_IDS

    def replay(self):
        rules = {r.relationship_type.key: str(r.id) for r in RelationshipTypeRule.objects.filter(relationship_type__model=self.model)}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for step in TRACE_REUSED_IDS.glob("*.json"):
            text = step.read_text(encoding="utf-8")
            for live, key in self.LIVE_RULE_IDS.items():
                text = text.replace(live, rules[key])
            (Path(directory.name) / step.name).write_text(text, encoding="utf-8")
        provider = IdTranslatingReplay(directory.name, inject={
            "extraction_correction": [no_more_corrections] * 2,
            "adjudication": [single_option_oracle] * 4,
            "gap_probe": [nothing_found] * 3,
            "gap_probe_correction": [no_more_claims] * 4,
        })
        return provider, self.run_reconcile(provider)

    def test_the_new_match_to_stage_claims_get_fresh_ids_and_their_own_correction(self):
        provider, _ = self.replay()

        corrections = [p for stage, p in zip(provider.requested, provider.payloads) if stage == "extraction_correction"]
        # The first correction re-asked the self-references under A1-A6 (and withdrew them).
        self.assertEqual({i["id"] for i in corrections[0]["invalid_items"] if i["issues"][0]["code"] == "self_reference"},
                         {"A1", "A2", "A3", "A4", "A5", "A6"})
        # The second correction re-asked the fixture rows, producing the match -> stage claims ...
        self.assertTrue({"S1#t3.r1", "S1#t3.r4"} <= {u["segment"]["segment_id"] for u in corrections[1]["uncovered_segments"]})
        later = [(n, i) for n, payload in enumerate(corrections) for i in payload["invalid_items"] if i["item"]["predicate"] == "is in stage"]
        self.assertEqual(len(later), 6)
        # ... which reach the next wave (the third correction) under fresh ids.
        self.assertEqual({n for n, _ in later}, {2})
        ids = {i["id"] for _, i in later}
        self.assertFalse(ids & {"A1", "A2", "A3", "A4", "A5", "A6"}, ids)
        self.assertEqual(len(ids), 6)
        self.assertEqual({i["issues"][0]["code"] for _, i in later}, {"excerpt_not_in_segment"})
        self.assertEqual({i["item"]["subject_eid"] for _, i in later}, {"E12", "E13", "E14", "E15", "E16", "E17"})
