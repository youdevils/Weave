"""
Phase 4 of .Documentation/reconcile-architecture-plan.md: gap triage
(structural lead / prose lead / no evidence) and the distinct negative
states (ai.services.reconcile.triage).
"""

from django.test import override_settings

from ai.services.orchestrator import run_ai_operation
from ai.services.reconcile import questions as q
from ai.services.reconcile import readings as rd
from ai.services.reconcile import triage as tg
from ai.tests.reference import norm
from ai.tests.support import approve, nothing_stated
from ai.tests.test_governance_contract import INTENT
from ai.tests.test_readings import ReadingFixture, dismiss_everything, no_claims, undecidable_answers
from ai.tests.test_reconcile_resilience import Responders


class TriageFixture(ReadingFixture):

    def state_of(self, analysis, name, relationship_key):
        cid = next(c for c, cluster in analysis.clusters.clusters.items() if cluster.name == name)
        requirement = next(r for r in analysis.scope.requirements[cid] if self.index.relationship_types[r.relationship_type_id].key == relationship_key)
        return analysis.requirement_states.get(requirement.requirement_id), analysis.triage.get(requirement.requirement_id), requirement


class TriageTests(TriageFixture):

    def test_no_lead_is_not_stated_without_any_ai_call(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())

        state, triaged, requirement = self.state_of(analysis, "McLean Park", "played_at")
        self.assertEqual((state, triaged.route), (tg.NOT_STATED, tg.TERMINAL))
        self.assertNotIn(requirement.requirement_id, {r.requirement_id for r in analysis.probe_requests})

    def test_prose_leads_go_to_a_probe_and_only_then_are_not_stated(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())

        state, triaged, requirement = self.state_of(analysis, "Semi-finals", "has_match")
        self.assertEqual((state, triaged.route), (tg.UNINVESTIGATED, tg.PROBE))
        self.assertIn(requirement.requirement_id, {r.requirement_id for r in analysis.probe_requests})
        self.assertIn("S1#9", triaged.prose)
        self.assertFalse(set(triaged.prose) & set(self.document.rows))

        self.rs.probed.add(requirement.requirement_id)
        self.rs.probe_outcomes[requirement.requirement_id] = "not_stated"
        self.rs.missing_evidence[requirement.requirement_id] = "complete"
        from ai.services.reconcile.analysis import run_analysis
        again = run_analysis(self.rs, index=self.index, bundle=self.bundle_)
        self.assertEqual(self.state_of(again, "Semi-finals", "has_match")[0], tg.NOT_STATED)

    def test_evidence_that_does_not_meet_the_rule_is_insufficient(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())

        self.assertEqual(self.state_of(analysis, "Quarter-final", "has_match")[0], tg.INSUFFICIENT)
        self.assertEqual(self.state_of(analysis, "Orangetheory Stadium", "played_at")[0], tg.INSUFFICIENT)

    def test_a_structural_lead_in_a_none_slot_is_challenged_never_not_stated(self):
        analysis = self.analyse_readings(self.readings(t3_relation="none"), items=self.prose_claims())

        state, triaged, requirement = self.state_of(analysis, "Forsyth Barr Stadium", "played_at")
        self.assertEqual((state, triaged.route), (tg.UNADJUDICATED, tg.QUESTION))
        self.assertEqual(triaged.slots, ["rd/S1#t3/relation/c2>c3"])
        challenge = [x for x in analysis.questions if x.question_id == rd.slot_question_key("rd/S1#t3/relation/c2>c3")]
        self.assertEqual(len(challenge), 1)  # one per slot, whatever number of venues point at it
        self.assertNotIn(requirement.requirement_id, {r.requirement_id for r in analysis.probe_requests})

    def test_an_upheld_none_lets_the_requirement_proceed(self):
        pin = q.Pin(option_id="none", basis="adjudicated", excerpt="Venue")
        analysis = self.analyse_readings(self.readings(t3_relation="none"), items=self.prose_claims(),
                                         pins={rd.slot_question_key("rd/S1#t3/relation/c2>c3"): pin})

        state, triaged, _ = self.state_of(analysis, "Forsyth Barr Stadium", "played_at")
        self.assertEqual((state, triaged.route), (tg.NOT_STATED, tg.TERMINAL))

    def test_a_not_stated_verdict_never_stands_over_a_structural_lead(self):
        analysis = self.analyse_readings(self.readings(t3_relation="none"), items=self.prose_claims())
        _, _, requirement = self.state_of(analysis, "Forsyth Barr Stadium", "played_at")
        self.rs.probed.add(requirement.requirement_id)
        self.rs.probe_outcomes[requirement.requirement_id] = "not_stated"
        self.rs.missing_evidence[requirement.requirement_id] = "complete"

        from ai.services.reconcile.analysis import run_analysis
        again = run_analysis(self.rs, index=self.index, bundle=self.bundle_)
        self.assertEqual(self.state_of(again, "Forsyth Barr Stadium", "played_at")[0], tg.UNADJUDICATED)

    def test_an_unresolved_row_exception_keeps_the_rows_items_open(self):
        open_ = self.analyse_readings(self.readings(t4_exception_decided=False), items=self.prose_claims())
        self.assertEqual(self.state_of(open_, "Pool A winner v Pool B runner-up", "has_team")[0], tg.UNADJUDICATED)
        self.assertEqual(self.state_of(open_, "Orangetheory Stadium", "played_at")[0], tg.UNADJUDICATED)

        key = rd.exception_question_key("rd/S1#t4/split/c2/placeholder")
        upheld = self.analyse_readings(self.readings(t4_exception_decided=False), items=self.prose_claims(),
                                       pins={key: q.Pin(option_id="exclude", basis="adjudicated", excerpt="Pool A winner")})
        self.assertEqual(self.state_of(upheld, "Pool A winner v Pool B runner-up", "has_team")[0], tg.NOT_STATED)
        self.assertEqual(self.state_of(upheld, "Orangetheory Stadium", "played_at")[0], tg.INSUFFICIENT)

    def test_every_blocked_item_reports_exactly_one_state(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())
        blocked = analysis.blocked_targets(self.index, self.rs.missing_evidence)

        self.assertTrue(blocked)
        for entry in blocked:
            with self.subTest(target=entry["target"]):
                self.assertIn(entry["state"], tg.STATES)
                self.assertTrue(all(m["state"] in tg.STATES for m in entry["missing_requirements"]))


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings", AI_TRACE_DIR=None)
class TriageWorkflowTests(TriageFixture):

    def test_the_flyer_probes_only_prose_and_reports_its_states(self):
        provider = Responders(reading=self.reading_responder(), extraction=self.prose_extraction, extraction_correction=dismiss_everything,
                              gap_probe=nothing_stated, gap_probe_correction=no_claims, adjudication=undecidable_answers,
                              verification=lambda payload: approve())
        result = run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=INTENT, assets=self.assets,
                                  provider=provider)

        states = {norm(b["target"]): b["state"] for b in result.blocked_targets}
        self.assertEqual(states[norm("McLean Park")], tg.NOT_STATED)
        self.assertEqual(states[norm("Quarter-final")], tg.INSUFFICIENT)
        self.assertEqual(states[norm("Orangetheory Stadium")], tg.INSUFFICIENT)
        self.assertEqual(states[norm("Semi-finals")], tg.NOT_STATED)
        probed = {r["entity"]["name"] for p in provider.payloads_for("gap_probe") for r in p["requirements"] if "entity" in r}
        self.assertNotIn("McLean Park", probed)  # no lead: no call
        for payload in provider.payloads_for("gap_probe"):
            self.assertFalse({s["segment_id"] for s in payload["segments"]} & set(self.document.rows))


class LiveFlyerRegressionTests(TriageFixture):
    """Gate run 2026-10-09 (all 5 readings-mode flyer runs): the title was read
    as the tournament, but no section relation tied it to the tables, so
    every target cascaded to blocked. The reverse section lead (a cell under a
    heading Read as the counterpart's kind) must challenge each omitted
    relation; answering the challenges reaches the reference outcome."""

    def without_title_relations(self):
        plan = self.table_plan()
        slots, _, exceptions = plan["S1#1"]
        plan["S1#1"] = (slots, [], exceptions)
        return self.readings(plan)

    def test_an_omitted_section_relation_is_challenged(self):
        analysis = self.analyse_readings(self.without_title_relations(), items=self.prose_claims())

        asked = {x.question_id for x in analysis.questions if x.kind == "reading_slot"}
        self.assertIn(rd.slot_question_key("rd/S1#1/section_relation/S1#t3.c1"), asked)  # Pool A/B -> the tournament
        self.assertIn(rd.slot_question_key("rd/S1#1/section_relation/S1#t1.c2"), asked)  # the teams -> the tournament
        self.assertEqual(self.state_of(analysis, "Pool A", "has_stage")[0], tg.UNADJUDICATED)  # never not_stated

    def test_answering_the_challenges_reaches_the_reference_outcome(self):
        from ai.tests.reference import assert_reference, load_spec, run_core

        answers = {rd.slot_question_key(f"rd/S1#1/section_relation/{c}"): q.Pin(option_id=o, basis="adjudicated", excerpt=TITLE_EXCERPT)
                   for c, o in [("S1#t1.c1", "has_stage:as_stated"), ("S1#t3.c1", "has_stage:as_stated"), ("S1#t4.c1", "has_stage:as_stated"),
                                *((f"S1#t1.c{k}", "has_team_2:as_stated") for k in range(2, 6))]}
        analysis = self.analyse_readings(self.without_title_relations(), items=self.prose_claims(), pins=answers)

        from ai.services.reconcile.compiler import compile_change_set
        from ai.tests.reference import outcome_from_change_set
        change_set, _ = compile_change_set(analysis, index=self.index)
        # Probes over the prose leads answer not_stated (what the live runs did).
        for _ in range(3):
            gaps = [r.requirement_id for r in analysis.probe_requests if r.requirement_id not in self.rs.probed]
            if not gaps:
                break
            self.rs.probed |= set(gaps)
            self.rs.probe_outcomes.update({g: "not_stated" for g in gaps})
            self.rs.missing_evidence.update({g: "complete" for g in gaps})
            from ai.services.reconcile.analysis import run_analysis
            analysis = run_analysis(self.rs, index=self.index, bundle=self.bundle_)
        change_set, _ = compile_change_set(analysis, index=self.index)
        blocked = analysis.blocked_targets(self.index, self.rs.missing_evidence)
        assert_reference(self, outcome_from_change_set(change_set, blocked, self.index), load_spec("international_flyer"))


TITLE_EXCERPT = "PACIFIC INTERNATIONAL RUGBY CHAMPIONSHIP 2027"
