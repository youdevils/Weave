"""
Readings, unit level -- the Phase 2 acceptance criteria of
.Documentation/reconcile-architecture-plan.md that need no workflow:
expansion, causal chain and I2, correction leverage, application safety,
ownership / prose eligibility, the Reading contract, and scaling.
"""

from dataclasses import replace

from ai.services.document.model import Cell, Row
from ai.services.evidence_bundle import EvidenceBundle
from ai.services.evidence_graph import EvidenceGraph
from ai.services.reconcile import questions as q
from ai.services.reconcile import readings as rd
from ai.services.reconcile.compiler import compile_change_set
from ai.services.reconcile.ingress import ingest
from ai.services.reconcile.responses import ElementReading, ReadingResult, ReadingSlotAnswer
from ai.services.reconcile.state import ReconcileState
from ai.services.reconcile.trace_policy import check_trace
from ai.tests.test_governance_contract import ent
from ai.tests.test_readings import ReadingFixture


class ExpansionTests(ReadingFixture):

    def test_no_reading_no_claims(self):
        expansion = rd.expand(self.document, [], self.bundle_, self.index)

        self.assertTrue(expansion.graph.is_empty())
        self.assertEqual((expansion.overlay.types, expansion.overlay.relations), ({}, {}))

    def test_one_slot_reads_every_row(self):
        expansion = rd.expand(self.document, self.readings(), self.bundle_, self.index)

        played_at = [a for a in expansion.graph.assertions if a.aid.startswith("x/S1#t3.") and a.aid.endswith("c2>c3")]
        self.assertEqual(len(played_at), 4)
        self.assertEqual({expansion.overlay.relations[a.aid][2][0] for a in played_at}, {"read:rd/S1#t3/relation/c2>c3"})
        self.assertEqual({tuple(a.basis_refs) for a in played_at}, {("rd/S1#t3@1",)})

    def test_ids_are_deterministic(self):
        first = rd.expand(self.document, self.readings(), self.bundle_, self.index).graph
        second = rd.expand(EvidenceBundle.from_assets(self.assets).document(), self.readings(), self.bundle_, self.index).graph

        self.assertEqual(sorted(first.ids()), sorted(second.ids()))
        self.assertIn("x/S1#t3.r1.c2", first.ids())
        self.assertIn("x/S1#t3.r1.c2/p1", first.ids())
        self.assertEqual(first.entity("x/S1#t3.r1.c2").provenance[0].locator, "S1#t3.r1.c2")

    def test_a_derived_claim_names_every_reading_it_depends_on(self):
        expansion = rd.expand(self.document, self.readings(), self.bundle_, self.index)

        participation = expansion.graph.assertion("x/S1#1/S1#t1.r1.c2")
        self.assertEqual(participation.basis_refs, ["rd/S1#1@1", "rd/S1#t1@1"])
        self.assertEqual(participation.support, "structural")
        self.assertIn("read:rd/S1#t1/role/c2", expansion.inputs[participation.aid])

    def test_a_placeholder_exception_excludes_only_that_slot(self):
        expansion = rd.expand(self.document, self.readings(), self.bundle_, self.index)

        names = {e.name for e in expansion.graph.entities}
        self.assertIn("Pool A winner v Pool B runner-up", names)  # the match itself is specific
        self.assertFalse({n for n in names if "winner" in n and " v " not in n})  # no placeholder teams
        excluded = [a for a in expansion.anomalies if a.slot_id == "rd/S1#t4/split/c2"]
        self.assertEqual({a.row_id for a in excluded}, {"S1#t4.r1", "S1#t4.r2"})
        self.assertTrue(all(a.resolved for a in excluded))

    def test_reading_conforms_never_rediscovers_meaning(self):
        # Without a declared exception the placeholders read like any row:
        # deterministic code never decides they are not teams (invariant 17).
        expansion = rd.expand(self.document, self.readings(t4_exception=False), self.bundle_, self.index)

        self.assertIn("Pool A winner", {e.name for e in expansion.graph.entities})

    def test_malformed_and_repeated_header_rows_are_never_expanded(self):
        readings = self.readings()
        table = self.document.tables["S1#t3"]

        def row(row_id, *texts):
            return Row(row_id=row_id, table_id="S1#t3", cells=tuple(
                Cell(cell_id=f"{row_id}.c{k}", row_id=row_id, column_id=f"S1#t3.c{k}", ordinal=k, text=t) for k, t in enumerate(texts, 1)))

        self.document.tables["S1#t3"] = replace(table, rows=(
            row("S1#t3.r1", "Stage", "Match", "Venue"),
            row("S1#t3.r2", "Pool C", "Italy v Wales", "Eden Park", "extra"),
            row("S1#t3.r3", "Pool C", "Italy against Wales", "Eden Park"),
        ))
        expansion = rd.expand(self.document, readings, self.bundle_, self.index)

        reasons = [(a.row_id, a.reason) for a in expansion.anomalies if a.row_id.startswith("S1#t3.")]
        self.assertIn(("S1#t3.r1", "header_repeat"), reasons)
        self.assertTrue(any(r == "S1#t3.r2" and "arity" in why for r, why in reasons))
        self.assertTrue(any(r == "S1#t3.r3" and "separator" in why for r, why in reasons))
        ids = expansion.graph.ids()
        self.assertNotIn("x/S1#t3.r1.c1", ids)
        self.assertNotIn("x/S1#t3.r2.c1", ids)
        self.assertNotIn("x/S1#t3.r3.c2/p1", ids)  # no split without the separator
        self.assertIn("x/S1#t3.r3.c2", ids)  # the match cell itself still reads


class GovernanceIntegrationTests(ReadingFixture):

    def test_reading_derived_claims_bypass_mapping(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())

        mapped = [d for d in analysis.ledger.decisions.values() if d.decision_id.startswith("map:x/")]
        self.assertTrue(mapped)
        self.assertEqual({d.basis for d in mapped}, {"reading"})
        self.assertFalse([x for x in analysis.questions if x.kind in ("assertion_mapping", "indirect_classification")])
        self.assertEqual({analysis.types[c].basis for c in analysis.clusters.clusters if c.startswith("x/")}, {"reading"})

    def test_every_compiled_change_walks_back_to_a_reading_slot_and_a_cell(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())
        change_set, trace = compile_change_set(analysis, index=self.index)

        self.assertEqual(check_trace(change_set, trace, analysis), [])
        played_at = next(a for a in change_set.actions if a.kind == "create_relationship" and a.relationship_type.key == "played_at")
        entry = trace.entries[played_at.action_id]
        claim = analysis.graph.assertion(entry.subject)
        decision = analysis.ledger.get(entry.subject)
        self.assertEqual(claim.origin, "reading")
        self.assertEqual(decision.kind, "structural")
        reads = [i for i in decision.inputs if i.startswith("read:")]
        self.assertIn("read:rd/S1#t3/relation/c2>c3", reads)
        self.assertTrue(all(analysis.ledger.get(r).kind == "claim" for r in reads))
        self.assertTrue(set(decision.detail["dem"]) <= set(self.document.cells))
        self.assertIn(claim.provenance[0].segment_id, self.document.rows)

    def test_one_slot_correction_re_reads_every_row(self):
        wrong = self.readings(t3_relation="none")
        before = self.analyse_readings(wrong, items=self.prose_claims())
        self.assertFalse([a for a in before.graph.assertions if a.aid.startswith("x/S1#t3.") and a.aid.endswith("c2>c3")])

        pin = q.Pin(option_id="played_at:as_stated", basis="adjudicated", excerpt="Venue")
        after = self.analyse_readings(wrong, items=self.prose_claims(), pins={rd.slot_question_key("rd/S1#t3/relation/c2>c3"): pin})

        corrected = [a for a in after.graph.assertions if a.aid.startswith("x/S1#t3.") and a.aid.endswith("c2>c3")]
        self.assertEqual(len(corrected), 4)
        self.assertEqual({tuple(a.basis_refs) for a in corrected}, {("rd/S1#t3@2",)})
        self.assertEqual(after.ledger.get("read:rd/S1#t3/relation/c2>c3").basis, "adjudicated")

    def test_revising_a_referenced_table_reading_re_expands_section_relations(self):
        pin = q.Pin(option_id="stage", basis="adjudicated", excerpt="Teams")
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims(), pins={rd.slot_question_key("rd/S1#t1/role/c1"): pin})

        self.assertEqual(analysis.graph.assertion("x/S1#1/S1#t1.r1.c2").basis_refs, ["rd/S1#1@1", "rd/S1#t1@2"])

    def test_an_undecidable_exception_is_one_grouped_question(self):
        analysis = self.analyse_readings(self.readings(t4_exception_decided=False), items=self.prose_claims())

        grouped = [x for x in analysis.questions if x.kind == "row_exception"]
        self.assertEqual(len(grouped), 1)
        self.assertEqual(set(grouped[0].subject_ids[1:]), {"S1#t4.r1", "S1#t4.r2"})
        self.assertTrue(any(not a.resolved for a in analysis.anomalies))

    def test_nothing_may_rest_on_an_undecided_reading_slot(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())
        change_set, trace = compile_change_set(analysis, index=self.index)
        # Inject the invariant violation: a traced chain whose Reading slot is undecidable.
        analysis.ledger.get("read:rd/S1#t3/relation/c2>c3").outcome = "undecidable"

        problems = [i.message for i in check_trace(change_set, trace, analysis)]
        self.assertTrue(any("not a decided Reading slot" in m for m in problems), problems)

    def test_a_derived_item_must_name_its_readings(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())
        change_set, trace = compile_change_set(analysis, index=self.index)
        analysis.graph.assertion("x/S1#t3.r1/c2>c3").basis_refs = []

        self.assertTrue(any("basis_refs" in i.message for i in check_trace(change_set, trace, analysis)))


class OwnershipTests(ReadingFixture):

    def test_a_table_reading_owns_its_table_and_rows(self):
        table_reading = [r for r in self.readings() if r.element_id == "S1#t3"]

        self.assertEqual(rd.owned_source_segments(table_reading, self.document),
                         {"S1#t3", "S1#t3.r1", "S1#t3.r2", "S1#t3.r3", "S1#t3.r4"})

    def test_a_section_reading_owns_only_the_heading_it_reads(self):
        readings = self.readings()
        title = next(r for r in readings if r.element_id == "S1#1")
        teams = next(r for r in readings if r.element_id == "S1#5")

        self.assertEqual(rd.owned_source_segments([title], self.document), {"S1#1"})
        self.assertEqual(rd.owned_source_segments([teams], self.document), set())  # 'Teams' names no entity
        self.assertFalse(set(title.owns) & set(self.document.cells))  # never a table's cells

    def test_prose_under_a_read_section_stays_prose(self):
        text = "TEAMS\n\nThe teams arrive in June.\n\nTeam | Coach\nAlpha | Ann\nBeta | Bo\n"
        bundle = EvidenceBundle.from_assets([{"name": "t.txt", "content": text, "mime_type": "text/plain"}])
        document = bundle.document()
        table_id = next(iter(document.tables))
        table = rd.Reading(reading_id=rd.reading_id(table_id), element_kind="table", element_id=table_id, status="validated")
        section = rd.Reading(reading_id="rd/S1#1", element_kind="section", element_id="S1#1", status="validated", owns=["S1#1"])

        eligible = rd.prose_eligible(document, [table, section])
        self.assertIn("S1#2", eligible)
        self.assertFalse(eligible & {table_id, *(r.row_id for r in document.tables[table_id].rows)})

    def test_structured_content_never_falls_back_to_prose(self):
        readings = [r for r in self.readings() if r.element_id != "S1#t3"]
        rejected = rd._unanswered(self.element("S1#t3"), self.document)

        for extra in ([], [rejected], [rejected.model_copy(update={"status": "superseded"})]):
            eligible = rd.prose_eligible(self.document, readings + extra)
            self.assertFalse(eligible & {"S1#t3", "S1#t3.r1"}, extra)
            self.assertIn("S1#t3.r1", rd.locked_segments(self.document, readings + extra))

    def test_not_a_table_returns_its_rows_to_prose(self):
        elements = {e.element_id: e for e in rd.skeleton(self.document, self.bundle_, self.index)}
        answer = ReadingResult(readings=[self.element_reading("S1#t2", None, not_a_table=("layout_grid", ["S1#t2", "S1#t2.r1"]))])
        reading = rd.apply_result(answer, {"S1#t2": elements["S1#t2"]}, self.document, self.bundle_, self.index, final=False).readings[0]

        self.assertEqual(reading.status, "not_a_table")
        self.assertIn("S1#t2.r1", rd.prose_eligible(self.document, [reading]))
        self.assertTrue(rd.expand(self.document, [reading], self.bundle_, self.index).graph.is_empty())

    def test_an_ai_claim_citing_a_read_table_row_is_refused(self):
        readings = self.readings()
        rs = ReconcileState(evidence_mode="readings", readings=readings, locked_segments=rd.locked_segments(self.document, readings))

        _, _, issues = ingest(EvidenceGraph(entities=[ent("V", "Eden Park", "venue", "S1#t3.r1")]), rs=rs, bundle=self.bundle_, origin="probe")
        self.assertEqual([i.code for i in issues], ["structured_segment"])


class ReadingContractTests(ReadingFixture):

    def validate(self, element_id, answer, elements=None):
        elements = elements or {e.element_id: e for e in rd.skeleton(self.document, self.bundle_, self.index)}
        return rd.apply_result(ReadingResult(readings=[answer]), {element_id: elements[element_id]}, self.document, self.bundle_,
                               self.index, final=False)

    def test_an_outside_shortlist_key_is_accepted_after_full_catalogue_validation(self):
        elements = {e.element_id: e for e in rd.skeleton(self.document, self.bundle_, self.index)}
        role = next(s for s in elements["S1#t3"].slots if s.slot_id == "rd/S1#t3/role/c3")
        role.options = [o for o in role.options if o != "venue"]  # the shortlist the AI saw lacked it
        answer = self.element_reading("S1#t3", self.table_plan())

        result = self.validate("S1#t3", answer, elements)
        self.assertEqual(result.issues, [])
        self.assertEqual(result.readings[0].slot("rd/S1#t3/role/c3").choice, "venue")
        next(s for s in answer.slots if s.slot_id == "rd/S1#t3/role/c3").choice = "stadium"
        self.assertTrue(self.validate("S1#t3", answer, elements).issues)

    def test_catalogue_references_are_strings_not_shortlist_enums(self):
        choice = ReadingSlotAnswer.model_json_schema()["properties"]["choice"]

        self.assertEqual(choice["type"], "string")
        self.assertNotIn("enum", choice)

    def test_an_illegal_relationship_is_a_shape_error_never_a_mapping_question(self):
        result = self.validate("S1#t3", self.element_reading("S1#t3", self.table_plan(t3_relation="has_stage:as_stated")))

        self.assertTrue(any("not legal between match and venue" in i.message for i in result.issues), [i.message for i in result.issues])

    def test_basis_rules(self):
        plan = self.table_plan()
        cases = {
            "header plus a cell": (["S1#t3.c2", "S1#t3.r1.c2"], True),
            "header without a cell": (["S1#t3.c2"], False),
            "a cell without header or heading": (["S1#t3.r1.c2"], False),
            "heading plus a cell": (["S1#15", "S1#t3.r1.c2"], True),
        }
        for name, (ids, ok) in cases.items():
            with self.subTest(name):
                answer = self.element_reading("S1#t3", plan)
                next(s for s in answer.slots if s.slot_id == "rd/S1#t3/role/c2").basis = self.basis(*ids)
                self.assertEqual(not self.validate("S1#t3", answer).issues, ok)
        # Headerless (the Teams table): the heading above it plus cells.
        self.assertFalse(self.validate("S1#t1", self.element_reading("S1#t1", plan)).issues)

    def test_a_header_only_table_reads_from_its_header_alone(self):
        bundle = EvidenceBundle.from_assets([{"name": "v.txt", "content": "Venues\nVenue | City\nEden Park | Auckland\n", "mime_type": "text/plain"}])
        document = bundle.document()
        table_id = next(iter(document.tables))
        slot = rd.Slot(slot_id="s", kind="role", columns=[f"{table_id}.c1"])
        document.tables[table_id] = replace(document.tables[table_id], rows=())

        self.assertTrue(rd.basis_sufficient(slot, [rd.SlotBasis(dem_id=f"{table_id}.c1", excerpt="Venue")], document, bundle))
        document.tables[table_id] = replace(document.tables[table_id], has_header=False)
        self.assertFalse(rd.basis_sufficient(slot, [rd.SlotBasis(dem_id="S1#1", excerpt="Venues")], document, bundle))

    def test_not_a_table_needs_a_reason_and_a_basis(self):
        result = self.validate("S1#t3", ElementReading(element_id="S1#t3", status="not_a_table", basis=self.basis("S1#t3")))

        self.assertTrue(result.issues)
        self.assertEqual(result.readings, [])

    def test_the_reading_schema_is_strict(self):
        from openai.lib._pydantic import to_strict_json_schema

        from ai.tests.test_structured_output_schema import _violations

        self.assertEqual(_violations(to_strict_json_schema(ReadingResult)), [])


class ScalingTests(ReadingFixture):
    """AI interpretation is O(schemas); expansion is O(rows)."""

    def fixture_document(self, n):
        rows = "\n".join(f"Pool {i} | Team {i}a v Team {i}b | Ground {i}" for i in range(n))
        return EvidenceBundle.from_assets([{"name": "f.txt", "content": f"Example fixtures\nStage | Match | Venue\n{rows}\n", "mime_type": "text/plain"}])

    def expanded(self, bundle):
        document = bundle.document()
        elements = {e.element_id: e for e in rd.skeleton(document, bundle, self.index)}
        t = next(iter(document.tables))
        plan = {t: ({"role/c1": ("stage", [f"{t}.c1", f"{t}.r1.c1"], {}), "role/c2": ("match", [f"{t}.c2", f"{t}.r1.c2"], {}),
                     "split/c2": ("team", [f"{t}.c2", f"{t}.r1.c2"], {"part_relation": "has_team:as_stated"}),
                     "role/c3": ("venue", [f"{t}.c3", f"{t}.r1.c3"], {}),
                     "relation/c1>c2": ("has_match:as_stated", [f"{t}.c1", f"{t}.r1.c1"], {}),
                     "relation/c1>c3": ("none", [f"{t}.c1", f"{t}.r1.c1"], {}),
                     "relation/c2>c3": ("played_at:as_stated", [f"{t}.c2", f"{t}.r1.c2"], {})}, [], [])}
        self.document, self.bundle_ = document, bundle
        readings = rd.apply_result(ReadingResult(readings=[self.element_reading(t, plan)]), {t: elements[t]}, document, bundle,
                                   self.index, final=False).readings
        return rd.expand(document, readings, bundle, self.index).graph

    def test_ten_times_the_rows_same_slots_same_calls_linear_expansion(self):
        small, large = self.fixture_document(4), self.fixture_document(40)
        small_elements = rd.skeleton(small.document(), small, self.index)
        large_elements = rd.skeleton(large.document(), large, self.index)

        self.assertEqual([len(e.slots) for e in small_elements], [len(e.slots) for e in large_elements])
        self.assertEqual(len(rd.plan_reading_batches(small_elements, 12_000)), len(rd.plan_reading_batches(large_elements, 12_000)))
        self.assertLessEqual(next(e for e in large_elements if e.kind == "table").payload["rows_shown"], 8)
        self.assertEqual(len(self.expanded(large).assertions), 10 * len(self.expanded(small).assertions))
