"""
The Adjudication contract for Reading challenges (live runs 2026-10-09,
gate-2026-10-09-flyer-readings-2: in all 5 readings-mode flyer runs the
Reading left out the title-to-table section relations; triage challenged
them, but the questions carried NO segments -- the slots did not exist yet --
so the model cited the source id 'S1', was refused twice, and its answers
were recorded as rejected; and with bare, unpruned options it chose
`has_team` (match -> team) where only `has_team_2` (tournament -> team)
is legal).

A challenge now carries its heading, table and representative rows, and
offers only the relationships legal between the two ends' types, labelled.
"""

from django.test import override_settings

from ai.services.orchestrator import run_ai_operation
from ai.services.reconcile import readings as rd
from ai.services.reconcile.responses import AdjudicationAnswer, AdjudicationResult, Citation
from ai.services.result_schema import OperationOutcome
from ai.tests.reference import assert_reference, load_spec, outcome_from_proposal
from ai.tests.support import approve, nothing_stated
from ai.tests.test_governance_contract import INTENT
from ai.tests.test_readings import ReadingFixture, dismiss_everything, no_claims
from ai.tests.test_reconcile_resilience import Responders


def live_like_adjudicator(record):
    """Answers as the live model did: the relationship it believes in
    (`has_team` for teams -- whichever team option is offered -- and
    `has_stage` for stages), citing the first segment it is given, or the
    source id 'S1' when it is given none."""

    def respond(payload):
        record.append(payload)
        texts = {s["segment_id"]: s["text"] for s in payload.get("segments", [])}
        answers = []
        for question in payload["questions"]:
            options = [o["option_id"] for o in question["options"]]
            wanted = next((o for o in options if o.startswith("has_team") and o.endswith(":as_stated")), None) \
                or next((o for o in options if o.startswith("has_stage") and o.endswith(":as_stated")), None) \
                or ("same" if "same" in options else "undecidable")
            cited = [s for s in question.get("segment_ids", []) if s in texts]
            citations = [Citation(segment_id=cited[0], excerpt=texts[cited[0]])] if cited else [Citation(segment_id="S1", excerpt="Teams")]
            answers.append(AdjudicationAnswer(question_id=question["question_id"], option_id=wanted, citations=citations))
        return AdjudicationResult(answers=answers)
    return respond


class ChallengeQuestionTests(ReadingFixture):

    def without_title_relations(self):
        plan = self.table_plan()
        slots, _, exceptions = plan["S1#1"]
        plan["S1#1"] = (slots, [], exceptions)
        return self.readings(plan)

    def challenges(self):
        analysis = self.analyse_readings(self.without_title_relations(), items=self.prose_claims())
        return analysis, {x.question_id: x for x in analysis.questions if x.kind == "reading_slot"}

    def test_a_challenge_on_an_omitted_slot_carries_its_evidence(self):
        from ai.services.stages.adjudication import question_segments

        analysis, questions = self.challenges()
        teams = questions[rd.slot_question_key("rd/S1#1/section_relation/S1#t1.c2")]

        segments = question_segments(teams, analysis)
        self.assertIn("S1#1", segments)  # the heading
        self.assertIn("S1#t1", segments)  # the table
        self.assertIn("S1#t1.r1", segments)  # a representative row
        self.assertTrue(all(self.bundle_.segment(s) is not None for s in segments))

    def test_a_challenge_offers_only_legal_labelled_relationships(self):
        _, questions = self.challenges()
        teams = questions[rd.slot_question_key("rd/S1#1/section_relation/S1#t1.c2")]
        stages = questions[rd.slot_question_key("rd/S1#1/section_relation/S1#t3.c1")]

        team_options = {o.option_id for o in teams.options}
        self.assertIn("has_team_2:as_stated", team_options)
        self.assertFalse({o for o in team_options if o.startswith("has_team:")})  # match -> team: incompatible
        self.assertEqual(team_options - {"none", "undecidable"}, {"has_team_2:as_stated"})
        label = next(o for o in teams.options if o.option_id == "has_team_2:as_stated")
        self.assertIn("Tournament", label.label)
        self.assertIn("Team", label.label)
        self.assertEqual({o.option_id for o in stages.options} - {"none", "undecidable"}, {"has_stage:as_stated"})


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings", AI_TRACE_DIR=None)
class ChallengeWorkflowTests(ChallengeQuestionTests):

    def test_the_live_failure_now_reaches_the_reference_outcome(self):
        plan = self.table_plan()
        slots, _, exceptions = plan["S1#1"]
        plan["S1#1"] = (slots, [], exceptions)  # the Reading omits every section relation, as live
        asked = []
        provider = Responders(reading=self.reading_responder(plan), extraction=self.prose_extraction,
                              extraction_correction=dismiss_everything, gap_probe=nothing_stated, gap_probe_correction=no_claims,
                              adjudication=live_like_adjudicator(asked), verification=lambda payload: approve())
        result = run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=INTENT, assets=self.assets,
                                  provider=provider)

        challenges = [x for p in asked for x in p["questions"] if x["question_id"].startswith("reading_slot:rd/S1#1/section_relation/")]
        self.assertTrue(challenges)
        self.assertTrue(all(x["segment_ids"] for x in challenges), "every challenge carries its segments")
        shown = {s["segment_id"] for p in asked for s in p["segments"]}
        self.assertTrue({"S1#1", "S1#t1"} <= shown)
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        assert_reference(self, outcome_from_proposal(result.proposal_id, result.blocked_targets), load_spec("international_flyer"))
