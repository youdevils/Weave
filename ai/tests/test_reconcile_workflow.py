"""
Staged Assisted Reconcile end to end (scripted provider), on the rugby
scenario that exposed the CandidateSet architecture's failure modes:

    Extraction (claims) -> analysis -> [Adjudication] -> [Gap Probe]
        -> compile -> Verification -> commit

Covers each stage's contract (what it is sent), item-level correction,
typed questions, gap probes, partial outcomes, Verification's cause-based
routing, the no-change and clarification paths, accounting, and that nothing
canonical changes before a human accepts the Proposal.
"""

import os
import unittest

from django.test import override_settings

from model.models.evidence_reference import EvidenceReference
from model.models.object import Object
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship import Relationship

from ai.models import AIExecution, AIExecutionStep
from ai.services.intent_frame import FrameAmendment
from ai.services.orchestrator import run_ai_operation
from ai.services.provider import ProviderError
from ai.services.result_schema import ExecutionStatus, OperationOutcome
from ai.tests.rugby import FLYER_ASSETS, INTENT, RugbyFixture
from ai.tests.support import (
    RaisingProvider,
    ScriptedProvider,
    answers,
    approve,
    assertion,
    entity,
    extraction,
    extraction_clarification,
    fact,
    frame,
    graph,
    nothing_stated,
    objection,
    probe,
    reject,
    verdict,
)

UUID_LIKE = "123e4567-e89b-12d3-a456-426614174000"


class ReconcileWorkflowTestCase(RugbyFixture):

    def run_reconcile(self, provider, *, intent=INTENT, assets=FLYER_ASSETS, **kwargs):
        return run_ai_operation(
            operation_id="reconcile", model=self.model, user=self.user, intent_text=intent,
            assets=assets, provider=provider, **kwargs,
        )

    def canonical_counts(self):
        return (
            Object.objects.filter(model=self.model).count(),
            Relationship.objects.filter(model=self.model).count(),
        )

    def proposal_changes(self, result):
        return list(ProposalChange.objects.filter(proposal_id=result.proposal_id))

    def created_names(self, result):
        return sorted(c.after["name"] for c in self.proposal_changes(result) if c.target_type == "Object" and c.operation == "create")

    def messages(self, result):
        return [f.message for f in result.findings]


class HappyPathTests(ReconcileWorkflowTestCase):

    def test_extraction_and_verification_produce_the_full_evidenced_proposal(self):
        provider = ScriptedProvider([self.flyer_extraction(), approve()])
        before = self.canonical_counts()

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "complete")
        self.assertEqual(provider.stages, ["extraction", "verification"])
        self.assertEqual(result.provider_calls, 2)
        self.assertEqual(result.refinement_cycles, 0)
        self.assertEqual(self.created_names(result), ["Eden Park", "Fiji", "Forsyth Barr Stadium", "Match 1", "New Zealand", "Pool Stage"])
        self.assertEqual(sum(1 for c in self.proposal_changes(result) if c.target_type == "Relationship"), 5)
        self.assertTrue(EvidenceReference.objects.filter(change__proposal_id=result.proposal_id, note="Eden Park capacity: 50000").exists())
        self.assertEqual(Proposal.objects.get(pk=result.proposal_id).status, Proposal.Status.WORKING)
        # Nothing canonical changes before a human accepts the Proposal.
        self.assertEqual(self.canonical_counts(), before)

    def test_each_ai_stage_receives_only_its_own_contract(self):
        provider = ScriptedProvider([self.flyer_extraction(), approve()])

        self.run_reconcile(provider)

        extraction_payload, verification_payload = provider.user_payloads
        self.assertIn("catalogue", extraction_payload)
        # Evidence arrives as addressable segments with structural context.
        segments = {s["segment_id"]: s for s in extraction_payload["segments"]}
        self.assertEqual(segments["S1#t1.r1"]["within"], ["S1#1", "S1#3", "S1#t1"])
        self.assertEqual(segments["S1#t1"]["text"], "Venue | City | Use")  # the header, citable by id
        self.assertTrue(all(s["source_id"] == "S1" for s in extraction_payload["segments"]))
        self.assertTrue(extraction_payload["frame_intent"])
        self.assertNotIn("objects", extraction_payload)
        for key in ("intent", "intent_frame", "evidence_segments", "decision_ledger", "changes", "blocked_targets",
                    "dismissed_segments", "uncovered_segments"):
            self.assertIn(key, verification_payload)
        self.assertNotIn("change_set", verification_payload)
        self.assertNotIn("catalogue", verification_payload)
        ledger_ids = {d["decision_id"] for d in verification_payload["decision_ledger"]}
        self.assertTrue({"map:A6", "fact:F2", "ident:E2"} <= ledger_ids)
        self.assertTrue(all(change["decision_ids"] for change in verification_payload["changes"]))

    def test_unrepresentable_and_indirect_evidence_surfaces_as_findings(self):
        result = self.run_reconcile(ScriptedProvider([self.flyer_extraction(), approve()]))

        messages = self.messages(result)
        self.assertIn("Not represented in the model: City = Auckland (Eden Park)", messages)
        self.assertTrue(any("Forsyth Barr Stadium" in m and "in general terms" in m for m in messages), messages)

    def test_sponsor_is_never_touched(self):
        result = self.run_reconcile(ScriptedProvider([self.flyer_extraction(), approve()]))

        self.assertNotIn(str(self.sponsor.id), {str(c.target_id) for c in self.proposal_changes(result)})

    def test_user_text_that_looks_like_an_identifier_passes_through_unchanged(self):
        intent = INTENT + f" Reference {UUID_LIKE}."
        provider = ScriptedProvider([self.flyer_extraction(), approve()])

        self.run_reconcile(provider, intent=intent)

        self.assertEqual(provider.user_payloads[0]["intent"], intent)


class ExtractionCorrectionTests(ReconcileWorkflowTestCase):

    def bad_capacity(self):
        result = self.flyer_extraction()
        next(f for f in result.evidence.facts if f.fid == "F2").provenance[0].excerpt = "Eden Park capacity: 60000"
        return result

    def test_only_the_invalid_item_is_re_asked_and_everything_else_is_frozen(self):
        fixed = extraction(frame(), fact("F2", "E6", "Capacity", "50000", excerpt="Eden Park capacity: 50000"))
        provider = ScriptedProvider([self.bad_capacity(), fixed, approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(provider.stages, ["extraction", "extraction_correction", "verification"])
        retry = provider.payloads_for("extraction_correction")[0]
        self.assertEqual([item["id"] for item in retry["invalid_items"]], ["F2"])
        self.assertEqual(retry["invalid_items"][0]["issues"][0]["code"], "excerpt_not_found")
        # Its segment names a target and nothing valid accounts for it yet, so
        # it is re-asked in the same correction pack.
        self.assertEqual([s["segment"]["segment_id"] for s in retry["uncovered_segments"]], ["S1#4"])
        self.assertIn("E6", [e["eid"] for e in retry["known_entities"]])
        eden = next(c for c in self.proposal_changes(result) if c.after and c.after.get("name") == "Eden Park")
        self.assertEqual(eden.after["attributes"], {"capacity": 50000})

    def test_an_item_that_fails_the_same_way_twice_is_dropped_not_re_asked(self):
        still_bad = extraction(frame(), fact("F2", "E6", "Capacity", "50000", excerpt="Eden Park capacity: 60000"))
        provider = ScriptedProvider([self.bad_capacity(), still_bad, nothing_stated, approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        # The venue segment nothing accounts for is still the venues target's
        # evidence gap: one targeted probe, then honestly left uncovered.
        self.assertEqual(provider.stages, ["extraction", "extraction_correction", "gap_probe", "verification"])
        self.assertEqual([(r["requirement_id"], r["segment_ids"][-1]) for r in provider.payloads_for("gap_probe")[0]["requirements"]],
                         [("target:T1", "S1#4")])
        eden = next(c for c in self.proposal_changes(result) if c.after and c.after.get("name") == "Eden Park")
        self.assertNotIn("attributes", eden.after)
        self.assertTrue(any("Ignored evidence claim 'F2'" in m for m in self.messages(result)), self.messages(result))

    def test_a_self_reference_is_re_asked_and_withdrawn_when_not_corrected(self):
        # An entity hidden in predicate text ("hosted the opening match") with
        # the claim pointing back at its own subject.
        with_loop = self.flyer_extraction()
        with_loop.evidence.assertions.append(assertion("A9", "E6", "hosted Match 1", "E6", excerpt="Eden Park"))
        provider = ScriptedProvider([with_loop, extraction(frame()), approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(provider.stages[:2], ["extraction", "extraction_correction"])
        retry = provider.payloads_for("extraction_correction")[0]
        [loop] = [i for i in retry["invalid_items"] if i["id"] == "A9"]
        self.assertEqual(loop["issues"][0]["code"], "self_reference")
        self.assertIn("withdraw the claim", loop["issues"][0]["message"])
        # Omitted by the correction = withdrawn: never part of the evidence.
        ledger = provider.payloads_for("verification")[0]["decision_ledger"]
        self.assertFalse([d for d in ledger if d["kind"] == "claim" and "A9" in d.get("subject_ids", [])])
        rejected = provider.payloads_for("verification")[0]["rejected_claims"]
        self.assertEqual([e["outcome"] for e in rejected if e["id"] == "A9"], ["invalid"])  # its fate, kept
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)

    def test_an_unanchored_claim_nothing_relates_is_dropped_without_a_re_ask(self):
        # Forsyth Barr Stadium and New Zealand: no segment names both, and no
        # heading/item pair relates them -- a correction could only withdraw it.
        unrelated = self.flyer_extraction()
        unrelated.evidence.assertions.append(assertion("A9", "E7", "hosts", "E4", excerpt="Forsyth Barr Stadium | Dunedin | Pool matches"))
        provider = ScriptedProvider([unrelated, approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(provider.stages, ["extraction", "verification"])
        [fate] = [e for e in provider.payloads_for("verification")[0]["rejected_claims"] if e["id"] == "A9"]
        self.assertEqual(fate["outcome"], "dropped")
        self.assertIn("does not mention both 'Forsyth Barr Stadium' and 'New Zealand'", fate["reason"])
        self.assertTrue(any(m.startswith("Ignored evidence claim 'A9':") for m in self.messages(result)), self.messages(result))
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)

    def test_an_unanchored_claim_a_segment_does_relate_is_still_re_asked(self):
        # Eden Park and Match 1 are related ("Match 1: ..., played at Eden Park"),
        # but the claim cites the venue row, which names no match.
        miscited = self.flyer_extraction()
        miscited.evidence.assertions.append(assertion("A9", "E6", "hosts", "E3", excerpt="Eden Park | Auckland | Opening match and final"))
        provider = ScriptedProvider([miscited, extraction(frame()), approve()])

        self.run_reconcile(provider)

        self.assertEqual(provider.stages[:2], ["extraction", "extraction_correction"])
        [entry] = [i for i in provider.payloads_for("extraction_correction")[0]["invalid_items"] if i["id"] == "A9"]
        self.assertEqual([i["code"] for i in entry["issues"]], ["unanchored_claim"])
        self.assertTrue(entry["relationship_anchors"]["direct"])

    def test_a_dangling_reference_is_repaired_deterministically(self):
        result_with_dangling = self.flyer_extraction()
        result_with_dangling.evidence.assertions.append(assertion("A9", "E3", "is refereed by", "E99", excerpt="Match 1"))
        provider = ScriptedProvider([result_with_dangling, approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(provider.stages, ["extraction", "verification"])
        self.assertTrue(any("'A9'" in m for m in self.messages(result)))

    def test_a_missing_endpoint_is_re_asked_not_dropped_as_dangling(self):
        # A list squeezed into one predicate (run 1d854489's A_NEW9).
        with_list = self.flyer_extraction()
        with_list.evidence.assertions.append(assertion("A9", "E3", "is played by the listed teams", "", excerpt="Match 1"))
        provider = ScriptedProvider([with_list, extraction(frame()), approve()])

        self.run_reconcile(provider)

        self.assertEqual(provider.stages[:2], ["extraction", "extraction_correction"])
        retry = provider.payloads_for("extraction_correction")[0]
        self.assertEqual([(i["id"], i["issues"][0]["code"]) for i in retry["invalid_items"]], [("A9", "missing_endpoint")])


class AdjudicationTests(ReconcileWorkflowTestCase):

    def setUp(self):
        super().setUp()
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park")
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park_old")

    def test_an_ambiguous_identity_is_asked_as_a_typed_question(self):
        provider = ScriptedProvider([
            self.flyer_extraction(),
            answers(("identity:E6", "eden_park", "Eden Park | Auckland")),
            approve(),
        ])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        question = provider.payloads_for("adjudication")[0]["questions"][0]
        self.assertEqual(question["kind"], "identity")
        self.assertEqual({o["option_id"] for o in question["options"]}, {"eden_park", "eden_park_old", "new", "undecidable"})
        self.assertNotIn("Eden Park", self.created_names(result))
        update = next(c for c in self.proposal_changes(result) if c.operation == "update")
        self.assertEqual(update.after, {"field": "attributes.capacity", "value": 50000})

    def test_an_invalid_answer_is_re_asked_alone(self):
        provider = ScriptedProvider([
            self.flyer_extraction(),
            answers(("identity:E6", "wembley", "Eden Park")),
            answers(("identity:E6", "eden_park", "Eden Park")),
            approve(),
        ])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        retry = provider.payloads_for("adjudication")[1]
        self.assertEqual([q["question_id"] for q in retry["questions"]], ["identity:E6"])
        self.assertEqual(retry["feedback"][0]["code"], "invalid_option")

    def test_an_undecidable_identity_blocks_only_what_depends_on_it(self):
        provider = ScriptedProvider([
            self.flyer_extraction(),
            answers(("identity:E6", "undecidable", "")),
            approve(),
        ])

        result = self.run_reconcile(provider)

        # Eden Park can't be identified, so Match 1 (needs played_at) and the
        # Pool Stage it supports are blocked; Forsyth Barr is independent.
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "partial")
        self.assertEqual(self.created_names(result), ["Forsyth Barr Stadium"])
        self.assertEqual([b["target"] for b in result.blocked_targets], ["Pool Stage"])
        # An identity question can't be answered by probing for more evidence.
        self.assertNotIn("gap_probe", provider.stages)
        self.assertTrue(any("could not be resolved" in m for m in self.messages(result)), self.messages(result))


class GapProbeTests(ReconcileWorkflowTestCase):

    def without_fiji(self):
        return self.flyer_extraction(include_fiji=False)

    def test_a_missed_counterpart_is_recovered_by_the_probe(self):
        requirement = "req:E3:{}:subject".format(self.has_team_rule_id())
        recovered = probe(
            entity("X1", "Fiji", "team", excerpt="Match 1: New Zealand v Fiji"),
            assertion("X2", "E3", "is played by", "X1", hint="has_team", excerpt="Match 1: New Zealand v Fiji"),
            verdicts=[verdict(requirement, "found", claim_ids=["X2"], segments_reviewed=["S1#2"])],
        )
        # The probe's hint is stripped, so OnyxJar asks what its wording means.
        meaning = answers(("predicate_mapping:is_played_by:match:team", "has_team:as_stated", "Match 1: New Zealand v Fiji"))
        provider = ScriptedProvider([self.without_fiji(), recovered, meaning, approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(provider.stages, ["extraction", "gap_probe", "adjudication", "verification"])
        self.assertEqual(result.completeness, "complete")
        self.assertIn("Fiji", self.created_names(result))
        payload = provider.payloads_for("gap_probe")[0]
        sent = payload["requirements"][0]
        self.assertIn("'Match 1'", sent["question"])
        self.assertEqual(sent["looking_for"]["relationship"], "Has Team")
        self.assertNotIn("_entity_ids", sent)
        # Local evidence only: the segments that mention Match 1 (+ neighbours), never the whole source.
        # The segment naming Match 1, and the heading it sits under (citable).
        self.assertEqual([s["segment_id"] for s in payload["segments"]], ["S1#1", "S1#2"])
        self.assertEqual(sent["segment_ids"], ["S1#1", "S1#2"])
        # The probe never sees relationship keys.
        self.assertNotIn("has_team", str(payload))

    def test_not_stated_gives_a_partial_proposal_with_material_findings(self):
        not_stated = probe(verdicts=[verdict("req:E3:{}:subject".format(self.has_team_rule_id()), "not_stated", segments_reviewed=["S1#2"])])
        provider = ScriptedProvider([self.without_fiji(), not_stated, approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "partial")
        self.assertEqual(self.created_names(result), ["Eden Park", "Forsyth Barr Stadium"])
        blocked = result.blocked_targets[0]
        self.assertEqual((blocked["target"], set(blocked["dependants"])), ("Pool Stage", {"Match 1", "New Zealand"}))
        self.assertTrue(any(f.severity == "material" and "Pool Stage" in f.message for f in result.findings))
        self.assertIn("Not included", Proposal.objects.get(pk=result.proposal_id).summary)
        # Verification was told about the block and did not have to object to it.
        self.assertEqual(provider.payloads_for("verification")[0]["blocked_targets"][0]["target"], "Pool Stage")

    def test_when_every_target_is_blocked_there_is_no_proposal(self):
        items = [i for i in self.flyer_items(include_fiji=False, include_forsyth_barr=False) if getattr(i, "eid", "") != "E6"
                 and getattr(i, "aid", "") != "A5" and getattr(i, "subject_id", "") != "E6"]
        stages_only = extraction(self.flyer_frame(), *items)
        not_stated = probe(verdicts=[verdict(f"req:E3:{rule}:subject", "not_stated") for rule in (self.has_team_rule_id(), self.played_at_rule_id())])

        provider = ScriptedProvider([stages_only, extraction(frame()), nothing_stated, approve()])

        result = self.run_reconcile(provider)

        # The venue rows nothing accounts for are re-asked, then probed as the
        # venues target's gap; a zero result is still reviewed before it ends.
        self.assertEqual(provider.stages, ["extraction", "extraction_correction", "gap_probe", "verification"])
        self.assertIn("target:T1", [r["requirement_id"] for r in provider.payloads_for("gap_probe")[0]["requirements"]])
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)
        # The requested venues are a block of their own: never silently dropped.
        self.assertEqual([b["target"] for b in result.blocked_targets], ["venues", "Pool Stage"])
        self.assertTrue(any("the request asks to add 'venues', but the evidence names none" in m for m in self.messages(result)))

    def has_team_rule_id(self):
        from model.models.relationship_type_rule import RelationshipTypeRule

        return RelationshipTypeRule.objects.get(relationship_type=self.has_team).id

    def played_at_rule_id(self):
        from model.models.relationship_type_rule import RelationshipTypeRule

        return RelationshipTypeRule.objects.get(relationship_type=self.played_at).id


class VerificationRoutingTests(ReconcileWorkflowTestCase):

    def test_evidence_misread_retracts_the_claim_and_recompiles(self):
        provider = ScriptedProvider([
            self.flyer_extraction(),
            reject(objection("decision", "F2", "evidence_misread", "The flyer's capacity line is for a different venue.")),
            approve(),
        ])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(provider.stages, ["extraction", "verification", "verification"])
        self.assertEqual(result.refinement_cycles, 1)
        eden = next(c for c in self.proposal_changes(result) if c.after and c.after.get("name") == "Eden Park")
        self.assertNotIn("attributes", eden.after)

    def test_missed_evidence_is_appended_and_reconciled(self):
        # Extraction, its correction and the venues target's probe all miss the
        # row; the reviewer still recovers it.
        provider = ScriptedProvider([
            self.flyer_extraction(include_forsyth_barr=False), extraction(frame()), nothing_stated,
            reject(objection("segment", "S1", "missed_evidence", "Forsyth Barr Stadium is listed as a venue.",
                             evidence=graph(entity("E7", "Forsyth Barr Stadium", "venue", hint="venue", excerpt="Forsyth Barr Stadium")))),
            approve(),
        ])

        result = self.run_reconcile(provider)

        self.assertIn("Forsyth Barr Stadium", self.created_names(result))

    def test_a_wrong_mapping_reenters_at_mapping(self):
        provider = ScriptedProvider([
            self.flyer_extraction(),
            reject(objection("decision", "fact:F2", "wrong_mapping", "That figure is not the capacity.", option_id="none")),
            approve(),
        ])

        result = self.run_reconcile(provider)

        eden = next(c for c in self.proposal_changes(result) if c.after and c.after.get("name") == "Eden Park")
        self.assertNotIn("attributes", eden.after)

    def test_a_frame_error_is_amended_from_the_intent(self):
        amendment = FrameAmendment(remove_target_ids=["T1"])
        provider = ScriptedProvider([
            self.flyer_extraction(),
            reject(objection("intent", "intent", "frame_error", "Only stages were asked for.", frame_amendment=amendment)),
            approve(),
        ])

        result = self.run_reconcile(provider)

        # Eden Park stays (Match 1 needs it); Forsyth Barr was only a venue target.
        self.assertIn("Eden Park", self.created_names(result))
        self.assertNotIn("Forsyth Barr Stadium", self.created_names(result))

    def test_an_unroutable_objection_is_corrected_by_the_reviewer(self):
        provider = ScriptedProvider([
            self.flyer_extraction(),
            reject(objection("decision", "no-such-decision", "wrong_mapping", "Hmm.")),
            approve(),
        ])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(provider.payloads_for("verification")[1]["feedback"][0]["code"], "unroutable_objection")

    def test_a_repeated_objection_ends_unresolved_with_findings(self):
        same = objection("decision", "F3", "evidence_misread", "Use is wrong.")
        provider = ScriptedProvider([self.flyer_extraction(), reject(same), reject(same)])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)
        self.assertIn("Use is wrong.", self.messages(result))

    def test_a_genuinely_ambiguous_intent_asks_for_clarification(self):
        provider = ScriptedProvider([
            self.flyer_extraction(),
            reject(objection("intent", "intent", "intent_ambiguous", "Two readings.", readings=["only pool venues", "all venues"])),
        ])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.NEEDS_USER_CLARIFICATION)
        self.assertIn("only pool venues", result.explanation)

    def test_minor_notes_never_block_the_proposal(self):
        result = self.run_reconcile(ScriptedProvider([self.flyer_extraction(), approve("Venue cities aren't modelled.")]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertIn("Venue cities aren't modelled.", self.messages(result))


class NoChangeAndClarificationTests(ReconcileWorkflowTestCase):

    def test_nothing_to_change_is_verified_before_no_change(self):
        provider = ScriptedProvider([extraction(frame()), approve()])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.NO_CHANGE_REQUIRED)
        self.assertEqual(provider.stages, ["extraction", "verification"])

    def test_evidence_already_consistent_with_the_model_is_no_change(self):
        provider = ScriptedProvider([
            extraction(frame(), entity("E1", "Qualifier Venue", "venue", hint="venue", excerpt="Qualifier Venue")),
            approve(),
        ])
        assets = [{"name": "notes.txt", "content": "Qualifier Venue hosted the qualifiers."}]

        self.assertEqual(self.run_reconcile(provider, assets=assets).outcome, OperationOutcome.NO_CHANGE_REQUIRED)

    def test_clarification_is_its_own_outcome(self):
        result = self.run_reconcile(ScriptedProvider([extraction_clarification("Which tournament?")]))

        self.assertEqual(result.outcome, OperationOutcome.NEEDS_USER_CLARIFICATION)
        self.assertEqual(result.explanation, "Which tournament?")


class AccountingTests(ReconcileWorkflowTestCase):

    def test_provider_and_deterministic_steps_are_recorded_in_order(self):
        provider = ScriptedProvider([self.flyer_extraction(), approve()], tokens_per_call=10)

        result = self.run_reconcile(provider)

        execution = AIExecution.objects.get(pk=result.execution_id)
        self.assertEqual(execution.usage["total_tokens"], 20)
        self.assertEqual(execution.provider_calls, 2)
        steps = list(AIExecutionStep.objects.filter(execution=execution))
        self.assertEqual([(s.stage, s.provider_call, s.decision) for s in steps], [
            ("extraction", True, "advance"), ("analysis", False, "advance"), ("compile", False, "advance"),
            ("verification", True, "finish"),
        ])
        self.assertEqual([s.sequence for s in steps], [1, 2, 3, 4])
        self.assertEqual(steps[-1].verdict, "approved")

    def test_explanation_call_is_outside_the_workflow_budget_and_still_counted(self):
        same = objection("decision", "F3", "evidence_misread", "Use is wrong.")
        provider = ScriptedProvider([self.flyer_extraction(), reject(same), reject(same)], tokens_per_call=10)

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertEqual(provider.generate_calls, 3)
        self.assertEqual(provider.explain_calls, 1)
        self.assertEqual(result.provider_calls, 4)

    @override_settings(AI_WORKFLOW_MAX_PROVIDER_CALLS=2, AI_TERMINAL_EXPLANATION_MAX_CALLS=1)
    def test_global_workflow_cap_bounds_the_whole_run(self):
        provider = ScriptedProvider([
            self.flyer_extraction(),
            reject(objection("decision", "F2", "evidence_misread", "Wrong venue.")),
        ])

        result = self.run_reconcile(provider)

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertEqual(provider.generate_calls, 2)

    def test_progress_is_reported_before_every_provider_call(self):
        seen = []

        self.run_reconcile(ScriptedProvider([self.flyer_extraction(), approve()]), on_progress=seen.append)

        self.assertEqual(seen, ["extraction", "verification"])

    def test_no_proposal_when_the_caller_withdraws_before_commit(self):
        result = self.run_reconcile(ScriptedProvider([self.flyer_extraction(), approve()]), should_commit=lambda: False)

        self.assertEqual(result.execution_status, ExecutionStatus.FAILED)
        self.assertIsNone(result.proposal_id)
        self.assertFalse(Proposal.objects.filter(model=self.model).exists())

    def test_provider_failure_is_a_technical_failure(self):
        result = self.run_reconcile(RaisingProvider(ProviderError("boom")))

        self.assertEqual(result.execution_status, ExecutionStatus.FAILED)
        self.assertEqual(result.outcome, OperationOutcome.FAILED)
        self.assertEqual(AIExecutionStep.objects.get(execution_id=result.execution_id).decision, "provider_error")


@unittest.skipUnless(os.environ.get("ONYXJAR_LIVE_AI_TESTS") == "1", "Set ONYXJAR_LIVE_AI_TESTS=1 to run against the real provider.")
class LiveRugbyTests(ReconcileWorkflowTestCase):
    """
    Opt-in, real-provider run of the rugby scenario. Asserts only invariants
    and the outcome class -- never exact actions (model output varies) -- and
    prints what to measure (plan section L): calls, tokens, hint acceptance,
    adjudication count and the indirect-reason distribution.
    """

    def test_live_rugby_reconcile(self):
        before = self.canonical_counts()

        result = self.run_reconcile(None)

        self.assertEqual(result.execution_status, ExecutionStatus.COMPLETED, result)
        self.assertIn(result.outcome, (OperationOutcome.READY_FOR_REVIEW, OperationOutcome.UNRESOLVED, OperationOutcome.NO_CHANGE_REQUIRED))
        self.assertLessEqual(result.provider_calls, 10)
        self.assertEqual(self.canonical_counts(), before)
        execution = AIExecution.objects.get(pk=result.execution_id)
        print(
            "\nLIVE RUGBY:", result.outcome.value, result.completeness, result.stage_summary,
            "tokens:", (execution.usage or {}).get("total_tokens"),
        )
        for finding in result.findings:
            print("  finding:", finding.severity, finding.message)
        for blocked in result.blocked_targets:
            print("  blocked:", blocked)
        if result.proposal_id:
            touched = {str(c.target_id) for c in self.proposal_changes(result)}
            self.assertNotIn(str(self.sponsor.id), touched)
            for change in self.proposal_changes(result):
                print("  ", change.operation, change.target_type, change.after)
