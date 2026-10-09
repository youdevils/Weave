"""
Hardening of the two remaining live failure modes (gate 2026-10-09):

- Flyer, 2/5 runs: the adjudicator answered `none` to "does the title's
  tournament have the Teams-table teams". The question had omitted the
  'Teams' section heading and the prose under the title ("Eight national
  teams"), and its prompt claimed the Reading had DECIDED none and nudged
  toward keeping it. Now it carries that evidence and asks neutrally.
- Rugby flyer, 0/5 in both modes: the request ("add the venues and stages
  ... to the 2027 Championship") is the only statement relating Pool Stage
  to the existing championship, and nothing asked about it. Now an
  `intent_link` question asks, offering only legal relationships; a quoted
  answer links the anchor to each evidenced item.
- Rugby flyer, 4/5 readings runs: the 'Venues' heading was read as a venue
  and compiled. A heading that only names a kind is not an entity of it.
"""

from django.test import override_settings

from ai.services.evidence_bundle import EvidenceBundle
from ai.services.orchestrator import run_ai_operation
from ai.services.reconcile import intent_links as il
from ai.services.reconcile import questions as q
from ai.services.reconcile import readings as rd
from ai.services.reconcile.analysis import run_analysis
from ai.services.reconcile.compiler import compile_change_set
from ai.services.reconcile.responses import (
    AdjudicationAnswer,
    AdjudicationResult,
    DemCitation,
    ElementReading,
    ReadingResult,
    ReadingSlotAnswer,
)
from ai.services.reconcile.state import ReconcileState
from ai.services.semantic.index import SemanticModelIndex
from ai.tests.reference import assert_reference, load_spec, norm, outcome_from_proposal
from ai.tests.rugby import FLYER_ASSETS, INTENT as RUGBY_INTENT, RugbyFixture
from ai.tests.support import approve, nothing_stated
from ai.tests.test_readings import ReadingFixture, dismiss_everything, no_claims
from ai.tests.test_readings_canonical import RugbyFlyerTests
from ai.tests.test_reconcile_resilience import Responders


class ChallengeEvidenceTests(ReadingFixture):

    def challenge(self):
        plan = self.table_plan()
        slots, _, exceptions = plan["S1#1"]
        plan["S1#1"] = (slots, [], exceptions)
        analysis = self.analyse_readings(self.readings(plan), items=self.prose_claims())
        return analysis, next(x for x in analysis.questions if x.question_id == rd.slot_question_key("rd/S1#1/section_relation/S1#t1.c2"))

    def test_the_teams_challenge_carries_the_section_heading_and_the_prose_under_the_title(self):
        from ai.services.stages.adjudication import question_segments

        analysis, question = self.challenge()
        segments = question_segments(question, analysis)

        self.assertIn("S1#5", segments)  # 'Teams'
        self.assertIn("S1#2", segments)  # 'Eight national teams. ...'
        self.assertTrue({"S1#1", "S1#t1", "S1#t1.r1"} <= set(segments))

    def test_the_prompt_is_accurate_and_neutral(self):
        _, question = self.challenge()

        self.assertIn("did not state any relationship", question.prompt)
        self.assertNotIn("Keep 'none'", question.prompt)
        self.assertNotIn("decided 'none'", question.prompt)
        self.assertIn("'Teams'", question.prompt)


class HeadingKindTests(ReadingFixture):

    def test_a_heading_that_names_a_kind_is_not_an_entity_of_it(self):
        elements = {e.element_id: e for e in rd.skeleton(self.document, self.bundle_, self.index)}
        answer = ElementReading(element_id="S1#14", slots=[ReadingSlotAnswer(
            slot_id="rd/S1#14/heading_entity", choice="venue", basis=[DemCitation(dem_id="S1#14", excerpt="Venues")])])

        issues = rd.apply_result(ReadingResult(readings=[answer]), {"S1#14": elements["S1#14"]}, self.document, self.bundle_, self.index,
                                 final=False).issues
        self.assertTrue(any("names the kind" in i.message for i in issues), [i.message for i in issues])

    def test_a_heading_naming_an_entity_is_still_read(self):
        elements = {e.element_id: e for e in rd.skeleton(self.document, self.bundle_, self.index)}
        answer = ElementReading(element_id="S1#1", slots=[ReadingSlotAnswer(
            slot_id="rd/S1#1/heading_entity", choice="tournament", basis=[DemCitation(dem_id="S1#1", excerpt="PACIFIC")])])

        self.assertEqual(rd.apply_result(ReadingResult(readings=[answer]), {"S1#1": elements["S1#1"]}, self.document, self.bundle_,
                                         self.index, final=False).issues, [])


class IntentLinkTests(RugbyFlyerTests):
    """The small rugby flyer, read in readings mode, whose prose extraction
    states nothing linking Pool Stage to the 2027 Championship."""

    def prose_without_link(self):
        return [item for item in self.prose_items() if getattr(item, "aid", None) != "A1"]

    def readings_for_table(self):
        bundle = EvidenceBundle.from_assets(FLYER_ASSETS)
        index = SemanticModelIndex.load(self.model)
        elements = {e.element_id: e for e in rd.skeleton(bundle.document(), bundle, index)}
        result = self.reading({"elements": [e.payload for e in elements.values()]})
        return bundle, index, rd.apply_result(result, elements, bundle.document(), bundle, index, final=False).readings

    def analyse(self, pins=None):
        bundle, index, readings = self.readings_for_table()
        from ai.tests.support import graph

        rs = ReconcileState(frame=self.flyer_frame(), graph=graph(*self.prose_without_link()), evidence_mode="readings",
                            readings=readings, intent_text=RUGBY_INTENT, pins=dict(pins or {}))
        rs.prose_scope = rd.prose_eligible(bundle.document(), readings)
        rs.locked_segments = rd.locked_segments(bundle.document(), readings)
        return run_analysis(rs, index=index, bundle=bundle), index

    def test_an_unstated_link_the_request_asks_for_is_asked_with_legal_options(self):
        analysis, _ = self.analyse()

        question = next(x for x in analysis.questions if x.kind == il.KIND)
        self.assertEqual(question.question_id, il.key("T2", "N1"))  # the stages -> the championship
        self.assertEqual({o.option_id for o in question.options} - {"none", "undecidable"}, {"has_stage:as_stated"})
        self.assertFalse([x for x in analysis.questions if x.question_id == il.key("T1", "N1")])  # no legal venue link

    def test_a_quoted_answer_links_the_anchor_to_each_item_without_duplicating_it(self):
        pin = q.Pin(option_id="has_stage:as_stated", basis="adjudicated", excerpt=RUGBY_INTENT)
        analysis, index = self.analyse({il.key("T2", "N1"): pin})
        change_set, trace = compile_change_set(analysis, index=index)

        links = [a for a in change_set.actions if a.kind == "create_relationship" and a.relationship_type.key == "has_stage"]
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].subject.model_dump(mode="json").get("key"), "championship_2027")  # the existing Object
        self.assertFalse([a for a in change_set.actions if a.kind == "create_object" and a.name == "2027 Championship"])
        from ai.services.reconcile.trace_policy import check_trace

        self.assertEqual(check_trace(change_set, trace, analysis), [])
        decision = analysis.ledger.get(trace.entries[links[0].action_id].subject)
        self.assertEqual((decision.kind, list(decision.inputs)), ("structural", [q.pin_decision_id(il.key("T2", "N1"))]))

    def test_claims_mode_never_asks(self):
        from ai.tests.support import graph

        bundle, index, readings = self.readings_for_table()
        rs = ReconcileState(frame=self.flyer_frame(), graph=graph(*self.prose_without_link()), intent_text=RUGBY_INTENT)
        analysis = run_analysis(rs, index=index, bundle=bundle)
        self.assertFalse([x for x in analysis.questions if x.kind == il.KIND])


def answer_intent_links(payload):
    answers = []
    for question in payload["questions"]:
        options = [o["option_id"] for o in question["options"]]
        if question["question_id"].startswith(il.KIND):
            choice = next(o for o in options if o not in ("none", "undecidable"))
            answers.append(AdjudicationAnswer(question_id=question["question_id"], option_id=choice, excerpt=RUGBY_INTENT))
        else:
            answers.append(AdjudicationAnswer(question_id=question["question_id"], option_id="undecidable"))
    return AdjudicationResult(answers=answers)


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings", AI_TRACE_DIR=None)
class IntentLinkWorkflowTests(IntentLinkTests):

    def test_the_rugby_flyer_reaches_its_spec_through_the_intent_link(self):
        from ai.tests.support import extraction

        provider = Responders(reading=self.reading, extraction=lambda payload: extraction(self.flyer_frame(), *self.prose_without_link()),
                              extraction_correction=dismiss_everything, gap_probe=nothing_stated, gap_probe_correction=no_claims,
                              adjudication=answer_intent_links, verification=lambda payload: approve())
        result = run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=RUGBY_INTENT,
                                  assets=FLYER_ASSETS, provider=provider)

        self.assertIn("adjudication", provider.requested)
        outcome = outcome_from_proposal(result.proposal_id, result.blocked_targets)
        self.assertNotIn(norm("Venues"), outcome.names_of())
        assert_reference(self, outcome, load_spec("rugby_flyer"))
