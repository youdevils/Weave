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

import tempfile
from pathlib import Path

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
from ai.services.semantic.index import SemanticModelIndex
from ai.services.tracing import ReplayProvider, load
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
from ai.tests.test_evidence_lifecycle import InternationalFlyerFixture
from ai.tests.test_reconcile_workflow import ReconcileWorkflowTestCase

TRACE = Path(__file__).parent / "fixtures" / "traces" / "international_flyer_gpt41"

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

    @override_settings(AI_RECONCILE_ADJUDICATION_MAX_ROUNDS=1)
    def test_a_spent_round_budget_defers_without_defaulting(self):
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
        provider = ScriptedProvider([self.first_wave(), self.includes_answer(), self.fiji_probe()])

        result = self.run_reconcile(provider)

        self.assertEqual(provider.stages, ["extraction", "adjudication", "gap_probe"])
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
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
            text = step.read_text(encoding="utf-8")
            for live, key in self.LIVE_RULE_IDS.items():
                text = text.replace(live, rules[key])
            (Path(directory.name) / step.name).write_text(text, encoding="utf-8")
        provider = ReplayProvider(directory.name, inject={"adjudication": [single_option_oracle] * 3,
                                                          "gap_probe_correction": [no_more_claims] * 2,
                                                          "extraction_correction": [no_more_corrections] * 2})
        return provider, self.run_reconcile(provider)

    def changes(self, result):
        return list(ProposalChange.objects.filter(proposal_id=result.proposal_id))

    def test_probe_claims_re_enter_adjudication_and_compile(self):
        provider, result = self.replay()

        self.assertEqual(provider.requested, [
            "extraction", "extraction_correction", "extraction_correction", "adjudication", "adjudication", "gap_probe",
            "gap_probe_correction", "adjudication", "gap_probe", "adjudication", "verification",
        ])
        # The request itself drives the search: the elided target excerpts are
        # repaired, so the venues/stages targets are kept -- and the rows nothing
        # accounted for are their gaps -- instead of an empty frame widening
        # scope to everything.
        first_probe = provider.payloads[provider.requested.index("gap_probe")]
        self.assertTrue({"target:T1", "target:T2"} <= {r["requirement_id"] for r in first_probe["requirements"]})
        verification = provider.payloads[provider.requested.index("verification")]
        self.assertEqual({t["target_id"]: t["status"] for t in verification["intent_targets"]}, {"T1": "evidenced", "T2": "evidenced"})
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "partial")
        self.assertEqual((result.stage_summary["adjudication"]["calls"], result.stage_summary["adjudication_correction"]["calls"]), (3, 1))
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

    @override_settings(AI_RECONCILE_ADJUDICATION_MAX_ROUNDS=1)
    def test_the_live_budget_shape_now_ends_honestly(self):
        provider, result = self.replay()

        # One round and its correction; later questions are deferred, never defaulted.
        self.assertEqual(provider.requested.count("adjudication"), 2)
        verification = provider.payloads[provider.requested.index("verification")]
        self.assertTrue(verification["open_decisions"])
        self.assertFalse([d for d in verification["decision_ledger"] if d["decision_id"].startswith("adj:") and d.get("basis") == "budget"])
        messages = [f.message for f in result.findings if f.severity == "material"]
        eden = next(m for m in messages if "'Eden Park'" in m)
        self.assertIn("relates it to 1 match(s)", eden)  # two statements, one match
        self.assertIn("not adjudicated", eden)
        self.assertNotIn("the evidence identifies 0", eden)
