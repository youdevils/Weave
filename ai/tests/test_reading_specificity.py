"""
The Reading specificity contract (live gate, 2026-10-09: in all 5 readings-mode
flyer runs the model answered `specificity: "generic"` on every slot, so the
named Stage / Match / Venue / Team columns became generic, nothing was
compilable, and every required change was missing).

    - a role column is SPECIFIC by default; there is no free specificity field
    - generic is an explicit role choice, "generic:<type key>", with a
      generic_reason -- never inferred, never on another slot kind
    - legitimate generic references keep working, as does the per-row
      `generic` exception
"""

from ai.services.reconcile import questions as q
from ai.services.reconcile import readings as rd
from ai.services.reconcile.compiler import compile_change_set
from ai.services.reconcile.responses import ReadingException, ReadingResult
from ai.tests.reference import assert_reference, load_spec, norm, outcome_from_change_set
from ai.tests.test_readings import ReadingFixture


class SpecificityContractTests(ReadingFixture):

    def elements(self):
        return {e.element_id: e for e in rd.skeleton(self.document, self.bundle_, self.index)}

    def validate(self, result: ReadingResult):
        elements = self.elements()
        return rd.apply_result(result, {r.element_id: elements[r.element_id] for r in result.readings}, self.document, self.bundle_,
                               self.index, final=False)

    def live_shaped(self, plan=None):
        """The ideal answers as the live provider sent them: every slot with
        specificity 'generic' (a field the contract no longer has)."""

        plan = plan or self.table_plan()
        raw = ReadingResult(readings=[self.element_reading(e, plan) for e in self.elements()]).model_dump(mode="json")
        for reading in raw["readings"]:
            for slot in reading["slots"]:
                slot["specificity"] = "generic"
        return ReadingResult.model_validate(raw)

    def test_named_columns_stay_specific_whatever_specificity_the_model_sends(self):
        answered = self.validate(self.live_shaped())

        self.assertEqual(answered.issues, [])
        roles = [s for r in answered.readings for s in r.slots if s.kind == "role" and s.choice not in (rd.NONE, rd.VALUE)]
        self.assertTrue(roles)
        self.assertEqual({s.specificity for s in roles}, {"specific"})
        expansion = rd.expand(self.document, answered.readings, self.bundle_, self.index)
        for name in ("Pool A", "New Zealand v Fiji", "Eden Park", "New Zealand"):
            self.assertEqual({e.specificity for e in expansion.graph.entities if e.name == name}, {"specific"}, name)

    def test_the_live_shaped_reading_compiles_the_reference_outcome(self):
        analysis = self.analyse_readings(self.validate(self.live_shaped()).readings, items=self.prose_claims())
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

        assert_reference(self, outcome_from_change_set(change_set, analysis.blocked_targets(self.index, self.rs.missing_evidence), self.index),
                         load_spec("international_flyer"))

    def test_generic_is_an_explicit_justified_role_choice(self):
        plan = self.table_plan()
        venues, relations, exceptions = plan["S1#t2"]
        venues = dict(venues)
        venues["role/c3"] = ("generic:match", ["S1#t2.c3", "S1#t2.r3.c3"], {"generic_reason": "'Pool matches' refers to matches without naming any."})
        plan["S1#t2"] = (venues, relations, exceptions)
        answered = self.validate(ReadingResult(readings=[self.element_reading("S1#t2", plan)]))

        self.assertEqual(answered.issues, [])
        slot = answered.readings[0].slot("rd/S1#t2/role/c3")
        self.assertEqual((slot.choice, slot.specificity), ("match", "generic"))
        expansion = rd.expand(self.document, answered.readings, self.bundle_, self.index)
        generic = [e for e in expansion.graph.entities if e.eid.startswith("x/S1#t2.") and e.eid.endswith(".c3")]
        self.assertTrue(generic)
        self.assertEqual({e.specificity for e in generic}, {"generic"})

    def test_a_legitimate_generic_column_is_never_compiled(self):
        plan = self.table_plan()
        venues, relations, exceptions = plan["S1#t2"]
        venues = dict(venues)
        venues["role/c3"] = ("generic:match", ["S1#t2.c3", "S1#t2.r3.c3"], {"generic_reason": "No match is named."})
        venues["relation/c1>c3"] = ("played_at:converse", ["S1#t2.c1", "S1#t2.c3", "S1#t2.r1.c1"], {})
        plan["S1#t2"] = (venues, relations, exceptions)
        analysis = self.analyse_readings(self.readings(plan), items=self.prose_claims())
        change_set, _ = compile_change_set(analysis, index=self.index)

        compiled = {norm(a.name) for a in change_set.actions if a.kind == "create_object"}
        self.assertNotIn(norm("Pool matches"), compiled)
        indirect = [m for aid, m in analysis.assertions.items() if aid.startswith("x/S1#t2.") and aid.endswith("c1>c3")]
        self.assertTrue(indirect)
        self.assertEqual({(m.outcome, m.reason) for m in indirect}, {("indirect", "intermediate_unidentified")})
        self.assertNotIn(norm("McLean Park"), compiled)  # a generic reference never satisfies its requirement

    def test_generic_without_a_reason_is_a_shape_error(self):
        plan = self.table_plan()
        teams, relations, exceptions = plan["S1#t3"]
        teams = dict(teams)
        teams["role/c2"] = ("generic:match", ["S1#t3.c2", "S1#t3.r1.c2"], {})
        plan["S1#t3"] = (teams, relations, exceptions)

        issues = self.validate(ReadingResult(readings=[self.element_reading("S1#t3", plan)])).issues
        self.assertTrue(any("generic_reason" in i.message for i in issues), [i.message for i in issues])

    def test_generic_on_any_other_slot_kind_is_a_shape_error(self):
        plan = self.table_plan()
        fixtures, relations, exceptions = plan["S1#t3"]
        fixtures = dict(fixtures)
        fixtures["split/c2"] = ("generic:team", ["S1#t3.c2", "S1#t3.r1.c2"],
                                {"part_relation": "has_team:as_stated", "generic_reason": "Teams in general."})
        plan["S1#t3"] = (fixtures, relations, exceptions)

        issues = self.validate(ReadingResult(readings=[self.element_reading("S1#t3", plan)])).issues
        self.assertTrue(any("only a role slot can be generic" in i.message for i in issues), [i.message for i in issues])

    def test_a_correction_can_make_a_column_generic_explicitly(self):
        pin = q.Pin(option_id="generic:venue", basis="adjudicated", excerpt="Venue")
        readings = rd.effective(self.readings(), {rd.slot_question_key("rd/S1#t2/role/c1"): pin})

        slot = next(r for r in readings if r.element_id == "S1#t2").slot("rd/S1#t2/role/c1")
        self.assertEqual((slot.choice, slot.specificity), ("venue", "generic"))

    def test_the_per_row_generic_exception_still_excludes_its_rows(self):
        plan = self.table_plan(t4_exception=False)
        slots, relations, _ = plan["S1#t4"]
        plan["S1#t4"] = (slots, relations, [ReadingException(row_ids=["S1#t4.r1", "S1#t4.r2"], slot_id="rd/S1#t4/split/c2",
                                                             kind="generic", reason="Pool positions, not teams.")])
        expansion = rd.expand(self.document, self.readings(plan), self.bundle_, self.index)

        self.assertFalse({e.name for e in expansion.graph.entities if "winner" in e.name and " v " not in e.name})
        self.assertEqual({a.reason for a in expansion.anomalies if a.slot_id == "rd/S1#t4/split/c2"}, {"exception:generic:decided"})

    def test_the_schema_offers_no_free_specificity(self):
        properties = ReadingResult.model_json_schema()["$defs"]["ReadingSlotAnswer"]["properties"]

        self.assertNotIn("specificity", properties)
        self.assertIn("generic_reason", properties)
