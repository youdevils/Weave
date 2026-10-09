"""
The Reconcile provider-call budget, scaled with the planned workload
(readings mode; ai.services.stages.reconcile_steps.workload_allowance):

    budget = AI_WORKFLOW_MAX_PROVIDER_CALLS
             + min(2 * max(0, R - 2) + max(0, E - 1), AI_WORKFLOW_MAX_EXTRA_PROVIDER_CALLS)

R / E = planned Reading / Extraction batches (capped by their stage limits).
Reading and Extraction calls are not checked against a reserve for what
follows, so the allowance keeps the reference reserve (7 calls after the
worst-case unchecked work, as on the international flyer) for every
permitted workload; planned work the budget still cuts is reported, and
such a result is never complete.
"""

from types import SimpleNamespace

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from ai.services.evidence_bundle import EvidenceBundle
from ai.services.operation_definitions import build_create_workflow, build_reconcile_workflow
from ai.services.reconcile import readings as rd
from ai.services.reconcile.state import ReconcileState
from ai.services.result_schema import OperationOutcome
from ai.services.semantic.index import SemanticModelIndex
from ai.services.stages.extraction import plan_batches
from ai.services.stages.reconcile_steps import (
    grant_workload_allowance,
    shortfall_finding,
    workload_allowance,
    worst_case_pre_analysis,
)
from ai.services.workflow.engine import WorkflowDefinition, WorkflowRun
from ai.tests.support import approve, assertion, entity, extraction, frame, target
from ai.tests.test_reconcile_convergence import LateRoundFixture, single_option_oracle
from ai.tests.test_reconcile_resilience import Responders

RESERVE = 7  # the international flyer's: 14 - worst_case_pre_analysis(2, 1)


def workflow_run(max_extra=7, base=14, mode="readings"):
    definition = WorkflowDefinition(stages={}, first_stage="x", stage_budgets={}, total_budget=base, explanation_budget=1,
                                    max_extra_calls=max_extra)
    run = WorkflowRun(operation=None, model=None, user=None, intent=None, bundle=None, provider=None, config=None,
                      execution=SimpleNamespace(id="test"), definition=definition)
    run.state.reconcile = ReconcileState(evidence_mode=mode)
    return run


class FormulaTests(SimpleTestCase):

    def test_the_allowance_table(self):
        table = {(1, 1): 0, (2, 1): 0, (3, 1): 2, (4, 1): 4, (2, 3): 2, (3, 2): 3, (4, 4): 7, (6, 6): 7}
        for (r, e), allowance in table.items():
            with self.subTest(reading_batches=r, extraction_batches=e):
                self.assertEqual(workload_allowance(r, e), allowance)
                run = workflow_run()
                run.state.reconcile.reading_batches = [[f"t{i}"] for i in range(r)]
                run.state.reconcile.batches = [[f"s{i}"] for i in range(e)]
                grant_workload_allowance(run)
                self.assertEqual(run.total_budget, 14 + allowance)

    def test_the_flyer_keeps_the_default(self):
        self.assertEqual(14 - worst_case_pre_analysis(2, 1), RESERVE)
        self.assertEqual(workload_allowance(2, 1), 0)

    def test_every_permitted_workload_keeps_the_reserve(self):
        # The guarantee, from the live settings: after the most Reading and
        # Extraction can spend unchecked, one Adjudication round and a full
        # Verification pass are always left (later Extraction correction
        # waves are checked by affords_recovery and reported if cut).
        base, cap = settings.AI_WORKFLOW_MAX_PROVIDER_CALLS, settings.AI_WORKFLOW_MAX_EXTRA_PROVIDER_CALLS
        for r in range(1, settings.AI_RECONCILE_READING_MAX_BATCHES + 1):
            for e in range(1, settings.AI_RECONCILE_EXTRACTION_MAX_BATCHES + 1):
                with self.subTest(reading_batches=r, extraction_batches=e):
                    self.assertLessEqual(workload_allowance(r, e), cap)
                    self.assertGreaterEqual(base + min(workload_allowance(r, e), cap) - worst_case_pre_analysis(r, e), RESERVE)

    @override_settings(AI_RECONCILE_READING_MAX_BATCHES=6)
    def test_a_workload_beyond_the_cap_is_recorded_and_reported_never_implied_covered(self):
        run = workflow_run()
        rs = run.state.reconcile
        rs.reading_batches = [[f"t{i}"] for i in range(6)]
        grant_workload_allowance(run)

        self.assertEqual(workload_allowance(6, 1), 8)
        self.assertEqual((run.extra_calls, rs.budget_shortfall["reserve_uncovered"]), (7, 1))
        self.assertIsNone(shortfall_finding(rs, run))  # nothing was cut (yet): not a partial result by itself
        rs.budget_shortfall["adjudication_deferred"] = ["q1"]
        self.assertIn("needed 1 call(s) more than the budget can grant", shortfall_finding(rs, run).message)


class IdempotentGrantTests(SimpleTestCase):

    def test_only_the_difference_is_ever_granted(self):
        run = workflow_run()

        self.assertEqual(run.grant_calls(2), 2)
        self.assertEqual(run.grant_calls(2), 0)
        self.assertEqual(run.grant_calls(5), 3)
        self.assertEqual(run.grant_calls(1), 0)  # never taken back
        self.assertEqual(run.grant_calls(20), 2)  # capped
        self.assertEqual((run.extra_calls, run.total_budget, run.remaining_calls()), (7, 21, 21))

    def test_reading_then_extraction_planning_grant_the_new_target_once(self):
        run = workflow_run()
        rs = run.state.reconcile
        rs.reading_batches = [["t1"], ["t2"], ["t3"]]

        grant_workload_allowance(run)  # after Reading planning: E assumed 1
        self.assertEqual(run.extra_calls, 2)
        rs.batches = [["s1"], ["s2"], ["s3"]]
        grant_workload_allowance(run)  # after Extraction planning
        self.assertEqual(run.extra_calls, 4)
        grant_workload_allowance(run)
        self.assertEqual(run.extra_calls, 4)
        self.assertEqual(rs.call_budget, {"base": 14, "reading_batches": 3, "extraction_batches": 3, "required": 4,
                                          "granted": 4, "total": 18})

    def test_claims_mode_and_create_are_never_scaled(self):
        run = workflow_run(mode="claims")
        run.state.reconcile.reading_batches = [["t1"], ["t2"], ["t3"], ["t4"]]
        grant_workload_allowance(run)
        self.assertEqual(run.total_budget, 14)

        with override_settings(AI_RECONCILE_EVIDENCE_MODE="claims"):
            self.assertEqual(build_reconcile_workflow().max_extra_calls, 0)
        with override_settings(AI_RECONCILE_EVIDENCE_MODE="readings"):
            self.assertEqual(build_reconcile_workflow().max_extra_calls, settings.AI_WORKFLOW_MAX_EXTRA_PROVIDER_CALLS)
        self.assertEqual(build_create_workflow().max_extra_calls, 0)


# -- a synthetic larger document --------------------------------------------------------

INTENT = "Add the venues named in the notes."
STATED = "New Zealand v Fiji is held at Eden Park."
FILLER = ("The organising committee reviewed the season calendar, the travel arrangements for officials and the "
          "volunteer rosters, and recorded that no further changes were required at this stage of planning. ")


def notes_document(tables=8, paragraphs=40) -> str:
    parts = ["# CUP NOTES 2027", ""]
    for k in range(1, tables + 1):
        parts += [f"## Section {k}", "", "Stage | Fixture | Ground"]
        parts += [f"Group {k} | Side {k}{chr(64 + n)} v Side {k}{chr(80 + n)} | Field {k}-{n}" for n in range(1, 9)]
        parts.append("")
    parts += ["## Notes", ""]
    # Note 1 names an extracted entity (so coverage asks about it); the rest name nothing.
    parts += ["Note 1. Eden Park still has to confirm its booking. " + FILLER * 4, ""]
    for n in range(1, paragraphs):
        parts += [f"Note {n + 1}. " + FILLER * 4, ""]
    parts += [STATED, ""]
    return "\n".join(parts)


def unread_then_undecidable(payload):
    """Every slot answered without a basis (invalid), then -- on the batch's
    one re-ask -- left undecidable: each Reading batch costs two calls."""

    correcting = bool(payload.get("feedback"))
    readings = []
    for element in payload["elements"]:
        slots = [{"slot_id": s["slot_id"], "choice": "undecidable" if correcting else "none"} for s in element["slots"]]
        readings.append({"element_id": element["element_id"], "slots": slots})
    return {"readings": readings}


def held_at_extraction(payload):
    """The one prose claim (match -> venue, worded 'is held at': its mapping
    needs Adjudication), every other segment dismissed -- except the first
    batch's first note, left for the correction wave."""

    segments = [s["segment_id"] for s in payload["segments"]]
    texts = {s["segment_id"]: s["text"] for s in payload["segments"]}
    items = []
    stated = next((sid for sid in segments if texts[sid] == STATED), None)
    if stated:
        items = [entity("E1", "Eden Park", "venue", hint="venue", excerpt="Eden Park"),
                 entity("E2", "New Zealand v Fiji", "match", hint="match", excerpt="New Zealand v Fiji"),
                 assertion("A1", "E2", "is held at", "E1", excerpt=STATED)]
        for item in items:
            item.provenance[0].segment_id = stated
    left = next((sid for sid in segments if texts[sid].startswith("Note 1.")), None)
    dismissed = [(sid, "Committee administration; names no venue.") for sid in segments if sid not in (stated, left)]
    result = extraction(frame([target("T1", "venues", "venues")]) if payload.get("frame_intent") else frame(), *items, dismissed=dismissed)
    return result


def dismiss_uncovered(payload):
    return {"intent_frame": {}, "evidence": {},
            "dismissed_segments": [{"segment_id": e["segment"]["segment_id"], "reason": "Committee administration; names no venue."}
                                   for e in payload["uncovered_segments"]]}


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings", AI_TRACE_DIR=None, PROPOSAL_MAX_LIVE_PER_MODEL=10_000)
class LargerDocumentTests(LateRoundFixture):
    """R=4 Reading batches (each needing its one correction), E=3 Extraction
    batches and one correction: 12 calls before analysis. At a fixed 14 the
    one Adjudication question cannot be afforded; scaled, it can."""

    INTENT = INTENT

    def setUp(self):
        super().setUp()
        self.assets = [{"name": "notes.txt", "content": notes_document()}]
        self.bundle = EvidenceBundle.from_assets(self.assets)

    def responders(self):
        return Responders(reading=unread_then_undecidable, extraction=held_at_extraction, extraction_correction=dismiss_uncovered,
                          adjudication=single_option_oracle, gap_probe=lambda p: {"claims": {}, "verdicts": [
                              {"requirement_id": r["requirement_id"], "status": "not_stated"} for r in p["requirements"]]},
                          gap_probe_correction=lambda p: {"claims": {}, "verdicts": []}, verification=lambda p: approve())

    def test_the_document_plans_four_reading_and_three_extraction_batches(self):
        index = SemanticModelIndex.load(self.model)
        document = self.bundle.document()
        elements = rd.skeleton(document, self.bundle, index)
        reading = rd.plan_reading_batches(elements, settings.AI_READING_BATCH_MAX_CHARS)
        prose = rd.prose_eligible(document, [])

        self.assertEqual(len(reading), 4)
        self.assertEqual(len(plan_batches(self.bundle, settings.AI_EXTRACTION_BATCH_MAX_CHARS, only=prose)), 3)

    def test_the_scaled_budget_leaves_room_to_adjudicate(self):
        provider = self.responders()
        result = self.run_reconcile(provider)

        pre = provider.requested[:provider.requested.index("extraction_correction") + 1]
        self.assertEqual((pre.count("reading"), pre.count("extraction"), len(pre)), (8, 3, 12))
        self.assertIn("adjudication", provider.requested)
        self.assertEqual(provider.requested[-1], "verification")
        self.assertGreater(result.provider_calls, 14)
        self.assertLessEqual(result.provider_calls, 14 + workload_allowance(4, 3))
        self.assertFalse([f for f in result.findings if f.message.startswith("Incomplete: the run's call budget")])

    @override_settings(AI_WORKFLOW_MAX_EXTRA_PROVIDER_CALLS=0)
    def test_a_fixed_budget_defers_the_decision_and_says_so(self):
        provider = self.responders()
        result = self.run_reconcile(provider)

        self.assertNotIn("adjudication", provider.requested)
        self.assertEqual(provider.requested[-1], "verification")
        self.assertEqual(result.provider_calls, 13)
        self.assertNotEqual((result.outcome, result.completeness), (OperationOutcome.READY_FOR_REVIEW, "complete"))
        cut = [f.message for f in result.findings if f.message.startswith("Incomplete: the run's call budget (14 calls)")]
        self.assertEqual(len(cut), 1)
        self.assertIn("decision(s) not adjudicated", cut[0])

    @override_settings(AI_RECONCILE_READING_MAX_BATCHES=2)
    def test_structure_left_unread_makes_the_result_partial(self):
        provider = self.responders()
        result = self.run_reconcile(provider)

        self.assertEqual(provider.requested.count("reading"), 4)
        self.assertNotEqual((result.outcome, result.completeness), (OperationOutcome.READY_FOR_REVIEW, "complete"))
        cut = [f.message for f in result.findings if f.message.startswith("Incomplete: the run's call budget")]
        self.assertEqual(len(cut), 1)
        self.assertIn("table/section element(s) not read", cut[0])

    @override_settings(AI_WORKFLOW_MAX_PROVIDER_CALLS=6)
    def test_an_exhausted_budget_never_ends_ready_for_review(self):
        provider = self.responders()
        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)
