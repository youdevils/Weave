"""
Regressions from the third live readings-mode flyer round
(.ai-traces/gate-2026-10-09-flyer-readings-3):

- 'Quarter-finals' (prose) and 'Quarter-final' (the fixtures table) stayed two
  stages with no question asked; the reference checker then judged the prose
  one. Now names differing only by plural raise a coreference QUESTION (never
  an auto-merge), and the checker selects the fixture-derived stage by its
  evidence, not by the first matching name.
- A merge of the table's 'Eden Park' with the prose 'Eden Park, Auckland'
  took the prose surface form; the table cell's name is now canonical.
- Run c1189594: Adjudication answered `none` with an empty / invalid
  citation, then corrected to the valid relationship -- but every answer also
  cited the heading-less table's own (empty) segment with an empty excerpt,
  so even the correction was refused and recorded as rejected.
"""

from django.test import override_settings

from ai.services.orchestrator import run_ai_operation
from ai.services.reconcile import questions as q
from ai.services.reconcile.responses import AdjudicationAnswer, AdjudicationResult, Citation
from ai.services.result_schema import OperationOutcome
from ai.services.stages.adjudication import answer_issue
from ai.tests.reference import Outcome, assert_reference, evaluate, load_spec, norm, outcome_from_proposal
from ai.tests.support import approve, nothing_stated
from ai.tests.test_governance_contract import INTENT, TITLE, cite, ent, rel
from ai.tests.test_readings import ReadingFixture, dismiss_everything, no_claims
from ai.tests.test_reconcile_resilience import Responders


class CoreferenceTests(ReadingFixture):

    def prose_with_quarter_finals(self):
        title = cite("S1#1", TITLE)
        return [*self.prose_claims(), ent("QFP", "Quarter-finals", "stage", "S1#8"),
                rel("HS_QFP", "T", "has stage", "QFP", "has_stage", [title, cite("S1#8", self.text("S1#8"))], support="structural")]

    def cluster_of(self, analysis, eid):
        return analysis.clusters.clusters[analysis.clusters.by_eid[eid]]

    def test_plural_variants_raise_a_coreference_question_never_a_merge(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_with_quarter_finals())

        self.assertNotEqual(analysis.clusters.by_eid["QFP"], analysis.clusters.by_eid["x/S1#t4.r1.c1"])
        asked = [x for x in analysis.questions if x.kind == "coreference" and set(x.subject_ids) & {"QFP"}]
        self.assertTrue(asked, [x.question_id for x in analysis.questions])
        self.assertEqual({analysis.graph.entity(s).name for s in asked[0].subject_ids}, {"Quarter-finals", "Quarter-final"})

    def test_a_same_answer_merges_under_the_table_cells_name(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_with_quarter_finals())
        question = next(x for x in analysis.questions if x.kind == "coreference" and "QFP" in x.subject_ids)

        merged = self.analyse_readings(self.readings(), items=self.prose_with_quarter_finals(),
                                       pins={question.question_id: q.Pin(option_id="same", basis="adjudicated", excerpt="Quarter-final")})
        cluster = self.cluster_of(merged, "QFP")
        self.assertEqual(merged.clusters.by_eid["QFP"], merged.clusters.by_eid["x/S1#t4.r1.c1"])
        self.assertEqual(cluster.name, "Quarter-final")
        self.assertIn("Quarter-finals", cluster.aliases)

    def test_claims_mode_never_asks_about_plural_variants(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_with_quarter_finals())
        self.rs.evidence_mode = "claims"
        from ai.services.reconcile.analysis import run_analysis

        legacy = run_analysis(self.rs, index=self.index, bundle=self.bundle_)
        self.assertFalse([x for x in legacy.questions if x.kind == "coreference" and "QFP" in x.subject_ids])
        self.assertTrue([x for x in analysis.questions if x.kind == "coreference" and "QFP" in x.subject_ids])

    def test_the_table_cells_name_is_canonical_in_a_merge_with_prose(self):
        prose_eden = ent("EP", "Eden Park, Auckland", "venue", "S1#10")
        prose_eden.aliases = ["Eden Park"]
        analysis = self.analyse_readings(self.readings(), items=[*self.prose_claims(), prose_eden])

        cluster = self.cluster_of(analysis, "EP")
        self.assertEqual(analysis.clusters.by_eid["EP"], analysis.clusters.by_eid["x/S1#t2.r1.c1"])
        self.assertEqual(cluster.name, "Eden Park")
        self.assertIn("Eden Park, Auckland", cluster.aliases)


class CheckerSelectionTests(ReadingFixture):

    def entry(self, name, state, has_match_evidenced):
        return {"target": name, "state": state, "missing_requirements": [
            {"relationship_type_key": "has_match", "counterpart_type_key": "match", "evidenced": has_match_evidenced, "state": state}]}

    def checks(self, *entries):
        outcome = Outcome()
        for entry in entries:
            outcome.blocked[norm(entry["target"])] = entry["state"]
            outcome.blocked_entries.append(entry)
        return {c.id: c for c in evaluate(outcome, load_spec("international_flyer"))}

    def test_the_fixture_derived_stage_is_judged_not_the_first_name(self):
        checks = self.checks(self.entry("Quarter-finals", "not_stated", 0), self.entry("Quarter-final", "insufficient_evidence", 2))

        self.assertTrue(checks["blocked:quarter_finals"].passed, checks["blocked:quarter_finals"].detail)

    def test_the_spec_is_not_weakened(self):
        wrong_state = self.checks(self.entry("Quarter-finals", "not_stated", 0), self.entry("Quarter-final", "not_stated", 2))
        no_fixture_stage = self.checks(self.entry("Quarter-finals", "not_stated", 0))

        self.assertFalse(wrong_state["blocked:quarter_finals"].passed)
        self.assertFalse(no_fixture_stage["blocked:quarter_finals"].passed)
        self.assertIn("evidenced", no_fixture_stage["blocked:quarter_finals"].detail)


class EmptyCitationTests(ReadingFixture):

    def test_an_empty_structural_segment_neither_supports_nor_fails_an_answer(self):
        options = {"has_team_2:as_stated", "none", "undecidable"}
        empty_only = [Citation(segment_id="S1#t1", excerpt="")]
        with_rows = [Citation(segment_id="S1#t1", excerpt=""), Citation(segment_id="S1#t1.r1", excerpt=self.text("S1#t1.r1"))]

        self.assertIsNotNone(answer_issue("q", "none", options, citations=empty_only, excerpt="No relationship is stated.",
                                          bundle=self.bundle_, intent_text=INTENT))
        self.assertIsNone(answer_issue("q", "has_team_2:as_stated", options, citations=with_rows, bundle=self.bundle_, intent_text=INTENT))


def none_then_corrected(record):
    """Run c1189594's adjudicator: first `none` citing only the empty table
    segment (with a free-text excerpt), then -- on correction -- the right
    relationship, still citing the empty table segment beside real rows."""

    def respond(payload):
        record.append(payload)
        texts = {s["segment_id"]: s["text"] for s in payload["segments"]}
        correcting = bool(payload.get("feedback"))
        answers = []
        for question in payload["questions"]:
            options = [o["option_id"] for o in question["options"]]
            if not question["question_id"].startswith("reading_slot:"):
                answers.append(AdjudicationAnswer(question_id=question["question_id"], option_id="undecidable"))
                continue
            if not correcting:
                answers.append(AdjudicationAnswer(question_id=question["question_id"], option_id="none",
                                                  citations=[Citation(segment_id="S1#t1", excerpt="")],
                                                  excerpt="Although teams are listed beside the title, no relationship is stated."))
                continue
            choice = next(o for o in options if o.endswith(":as_stated") and o.split(":")[0] in ("has_team_2", "has_stage"))
            rows = [s for s in question["segment_ids"] if s in texts and texts[s].strip()]
            answers.append(AdjudicationAnswer(question_id=question["question_id"], option_id=choice,
                                              citations=[Citation(segment_id="S1#t1", excerpt=""),
                                                         *(Citation(segment_id=s, excerpt=texts[s]) for s in rows[:2])]))
        return AdjudicationResult(answers=answers)
    return respond


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings", AI_TRACE_DIR=None)
class NoneThenCorrectedWorkflowTests(ReadingFixture):

    def test_invalid_none_is_rejected_and_the_correction_is_accepted_and_compiles(self):
        plan = self.table_plan()
        slots, _, exceptions = plan["S1#1"]
        plan["S1#1"] = (slots, [], exceptions)  # the Reading omits the section relations, as live
        asked = []
        provider = Responders(reading=self.reading_responder(plan), extraction=self.prose_extraction,
                              extraction_correction=dismiss_everything, gap_probe=nothing_stated, gap_probe_correction=no_claims,
                              adjudication=none_then_corrected(asked), verification=lambda payload: approve())
        result = run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=INTENT, assets=self.assets,
                                  provider=provider)

        self.assertGreaterEqual(len(asked), 2)
        self.assertTrue(asked[1].get("feedback"), "the invalid `none` answers were sent back")
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        assert_reference(self, outcome_from_proposal(result.proposal_id, result.blocked_targets), load_spec("international_flyer"))
