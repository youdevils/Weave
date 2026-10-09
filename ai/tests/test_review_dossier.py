"""
Phase 5 of .Documentation/reconcile-architecture-plan.md: Verification in
readings mode reviews a bounded causal dossier (ai.services.stages.review)
-- what caused the changes, what prevented the rest, and the disputes
OnyxJar detected itself -- never the historical ledger.

The model's own judgement is live behaviour; what CI pins is that every
seeded defect reaches the reviewer as an explicit, routable entry.
"""

import json

from django.test import override_settings

from ai.services.orchestrator import run_ai_operation
from ai.services.reconcile import readings as rd
from ai.services.reconcile.compiler import compile_change_set
from ai.services.stages import prompts
from ai.services.stages.review import disputes
from ai.tests.support import approve, nothing_stated
from ai.tests.test_governance_contract import INTENT
from ai.tests.test_readings import ReadingFixture, dismiss_everything, no_claims, undecidable_answers
from ai.tests.test_reconcile_resilience import Responders as _Responders


class Responders(_Responders):
    """Also records each call's system prompt."""

    def generate_structured(self, *, system_prompt, **kwargs):
        self.system_prompts = [*getattr(self, "system_prompts", []), system_prompt]
        return super().generate_structured(system_prompt=system_prompt, **kwargs)


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings", AI_TRACE_DIR=None)
class DossierTests(ReadingFixture):

    def review(self, plan=None):
        provider = Responders(reading=self.reading_responder(plan), extraction=self.prose_extraction, extraction_correction=dismiss_everything,
                              gap_probe=nothing_stated, gap_probe_correction=no_claims, adjudication=undecidable_answers,
                              verification=lambda payload: approve())
        run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=INTENT, assets=self.assets, provider=provider)
        self.provider = provider
        return provider.payloads_for("verification")[-1]

    def test_the_reviewer_sees_causes_never_the_ledger(self):
        dossier = self.review()

        self.assertNotIn("decision_ledger", dossier)
        self.assertEqual(set(dossier["questions"]), {"Q1", "Q2"})
        self.assertIn(prompts.REVIEW, self.provider_system_prompt())
        played_at = next(d for d in dossier["causes_of_changes"]["reading_decisions"] if d["decision_id"] == "read:rd/S1#t3/relation/c2>c3")
        # The 4 played_at relationships, and the matches and venues whose
        # inclusion rests on them (their requirements are met through them).
        self.assertEqual(played_at["outcome"], "played_at:as_stated")
        self.assertGreaterEqual(played_at["changes_resting_on_it"], 4)
        self.assertLessEqual(len(played_at["sample_changes"]), 3)
        self.assertTrue(played_at["excerpts"])  # its structural basis, verbatim

    def provider_system_prompt(self):
        return "" if not hasattr(self.provider, "system_prompts") else self.provider.system_prompts[-1]

    def test_every_block_arrives_with_its_state_and_leads(self):
        dossier = self.review()
        blocks = {b["target"]: b for b in dossier["causes_of_blocks"]}

        self.assertEqual(blocks["McLean Park"]["state"], "not_stated")
        self.assertEqual(blocks["Orangetheory Stadium"]["state"], "insufficient_evidence")
        self.assertTrue(all(m["state"] for b in blocks.values() for m in b["missing_requirements"]))

    def test_the_dossier_is_bounded(self):
        dossier = self.review()
        size = len(json.dumps(dossier))

        # A performance objective, not a gate (plan, section 7): record it.
        print(f"\nreview dossier on the flyer: {size} chars")
        self.assertLess(size, 60_000)
        cited = {s["segment_id"] for s in dossier["segments"]}
        self.assertLess(len(cited), len(list(self.bundle_.segments())))  # only what entries cite

    def test_a_reading_that_ignores_the_match_column_reaches_the_reviewer_as_a_dispute(self):
        plan = self.table_plan()
        slots, relations, exceptions = plan["S1#t3"]
        slots = dict(slots)
        slots["role/c2"] = ("none", ["S1#t3.c2", "S1#t3.r1.c2"], {})
        slots["split/c2"] = ("none", ["S1#t3.c2", "S1#t3.r1.c2"], {})
        slots["relation/c1>c2"] = ("none", ["S1#t3.c1", "S1#t3.c2", "S1#t3.r1.c1"], {})
        slots["relation/c2>c3"] = ("none", ["S1#t3.c2", "S1#t3.c3", "S1#t3.r1.c2"], {})
        plan["S1#t3"] = (slots, relations, exceptions)
        dossier = self.review(plan)

        challenged = [d for d in dossier["disputes"] if d["kind"] == "lead_into_undecided_or_none" and d["slot_id"] == "rd/S1#t3/role/c2"]
        self.assertTrue(challenged, dossier["disputes"])
        # Ignored by the Reading -- or, once the challenge was answered
        # 'undecidable' (the scripted adjudicator), unread: never silent.
        self.assertTrue({"dem_id": "S1#t3.c2", "slot_id": "rd/S1#t3/role/c2"} in dossier["ignored_structure"]
                        or {"dem_id": "S1#t3.c2", "reading_id": "rd/S1#t3"} in dossier["unread_structure"], dossier["unread_structure"])
        self.assertIn("reading_slot:rd/S1#t3/role/c2", {x["question_id"] for p in self.provider.payloads_for("adjudication") for x in p["questions"]})


class DisputeTests(ReadingFixture):

    def test_a_not_stated_over_a_structural_lead_is_a_dispute(self):
        analysis = self.analyse_readings(self.readings(t3_relation="none"), items=self.prose_claims())
        requirement_id = next(r for r, t in analysis.triage.items() if t.route == "question")
        analysis.probe_outcomes[requirement_id] = "not_stated"

        kinds = {(d["kind"], d.get("requirement_id")) for d in disputes(analysis, self.rs, bundle=self.bundle_)}
        self.assertIn(("not_stated_over_structural_lead", requirement_id), kinds)

    def test_a_not_a_table_on_a_regular_table_is_a_dispute(self):
        readings = [r for r in self.readings() if r.element_id != "S1#t3"]
        readings.append(rd.Reading(reading_id="rd/S1#t3", element_kind="table", element_id="S1#t3", status="not_a_table",
                                   not_a_table_reason="layout_grid"))
        analysis = self.analyse_readings(readings, items=self.prose_claims())

        self.assertIn("not_a_table_on_a_conforming_table", {d["kind"] for d in disputes(analysis, self.rs, bundle=self.bundle_)})

    def test_a_change_resting_on_an_undecidable_slot_reaches_the_reviewer_as_an_invariant_violation(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())
        change_set, trace = compile_change_set(analysis, index=self.index)
        analysis.ledger.get("read:rd/S1#t3/relation/c2>c3").outcome = "undecidable"

        found = disputes(analysis, self.rs, bundle=self.bundle_, change_set=change_set, trace=trace)
        self.assertTrue(any(d["kind"] == "invariant_violation" for d in found))

    def test_repeated_anomalies_are_a_dispute(self):
        analysis = self.analyse_readings(self.readings(t4_exception_decided=False), items=self.prose_claims())

        self.assertIn("repeated_anomaly", {d["kind"] for d in disputes(analysis, self.rs, bundle=self.bundle_)})
