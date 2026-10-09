"""
Reconcile's deterministic core (ai.services.reconcile), driven directly from
claims -- no provider anywhere. Covers the plan's case tables:

- I2: OnyxJar derives structure, never meaning -- no deterministic reversal,
  same-type orientation flagged, ESC selects and never adds, every compiled
  action traced to claims (TracePolicy);
- C2/C4: ambiguity is preserved (ambiguous -> question -> unresolved, never
  silently unmapped); lexical identity only when unique;
- C3: the three `indirect` reasons, with source / mapping / reason layers;
- C7: corroborated / distinct / superseded / candidate_conflict -> conflict;
- D: blocked targets, blocked dependants, independent targets still compile;
- removal only on an explicit, confirmed removal claim.
"""

from ai.services.evidence_graph import EvidenceGraph
from ai.services.reconcile import questions as q
from ai.services.reconcile.analysis import run_analysis
from ai.services.reconcile.compiler import compile_change_set
from ai.services.reconcile.ledger import Ledger
from ai.services.reconcile.state import ReconcileState
from ai.services.reconcile.trace_policy import check_trace
from ai.services.semantic.index import SemanticModelIndex
from ai.services.evidence_bundle import EvidenceBundle
from ai.tests.rugby import FLYER_ASSETS, RugbyFixture
from ai.tests.support import assertion, entity, fact, frame, graph, target


# Evidence for the focused cases: one statement per segment, so every claim
# below cites text that actually states it (L2 grounding).
NOTES = """Eden Park hosts Match 1.

Match 1 was staged at Eden Park.

New Zealand is a rival of Fiji.

Pool Stage includes Match 1.

Pool Stage is held at Forsyth Barr Stadium.

New Zealand plays at Eden Park.

Eden Park capacity: 50000 as of 2027.

Eden Park seating: 42000 in 2019.

Eden Park capacity: 48000.

Eden Park capacity was corrected to 50000.

Acme Corp no longer sponsors the championship."""


class PipelineTestCase(RugbyFixture):
    text = None

    def analyse(self, items=None, *, intent_frame=None, pins=None, **state):
        rs = ReconcileState(
            frame=intent_frame if intent_frame is not None else self.flyer_frame(),
            graph=graph(*(items if items is not None else self.flyer_items())),
            pins=dict(pins or {}),
            **state,
        )
        self.rs = rs
        assets = [{"name": "notes.txt", "content": self.text}] if self.text else FLYER_ASSETS
        return run_analysis(rs, index=SemanticModelIndex.load(self.model), bundle=EvidenceBundle.from_assets(assets))

    def compile(self, analysis):
        return compile_change_set(analysis, index=SemanticModelIndex.load(self.model))

    def cid(self, analysis, name):
        return next(c for c, cluster in analysis.clusters.clusters.items() if cluster.name == name)

    def outcome(self, analysis, name):
        return analysis.scope.outcomes.get(self.cid(analysis, name))

    @staticmethod
    def pin(option, basis="adjudicated", excerpt="x"):
        return q.Pin(option_id=option, basis=basis, excerpt=excerpt)


class FlyerTests(PipelineTestCase):

    def test_the_flyer_compiles_the_full_evidenced_chain_with_no_questions(self):
        analysis = self.analyse()

        self.assertEqual(analysis.questions, [])
        self.assertEqual(analysis.probe_requests, [])
        for name in ("Pool Stage", "Match 1", "New Zealand", "Fiji", "Eden Park", "Forsyth Barr Stadium"):
            self.assertEqual(self.outcome(analysis, name), "selected", name)
        self.assertEqual(analysis.identities[self.cid(analysis, "2027 Championship")].outcome, "existing")

        change_set, trace = self.compile(analysis)
        kinds = [a.kind for a in change_set.actions]
        self.assertEqual(kinds.count("create_object"), 6)
        self.assertEqual(kinds.count("create_relationship"), 5)
        self.assertEqual(check_trace(change_set, trace, analysis), [])
        self.assertEqual(analysis.ledger.i2_violations(), [])
        eden = next(a for a in change_set.actions if a.kind == "create_object" and a.name == "Eden Park")
        self.assertEqual([v.model_dump(exclude_none=True) for v in eden.attributes], [{"key": "capacity", "number_value": 50000}])

    def test_forsyth_barrs_pool_matches_are_intermediate_unidentified_with_three_layers(self):
        analysis = self.analyse()

        decision = analysis.ledger.get("map:A6")
        self.assertEqual((decision.outcome, decision.reason), ("indirect", "intermediate_unidentified"))
        self.assertEqual(decision.source["predicate"], "hosts")
        self.assertEqual(decision.mapping["option"], "played_at:converse")
        self.assertTrue(any("Forsyth Barr Stadium" in f.message and "in general terms" in f.message for f in analysis.findings))

    def test_capacity_maps_lexically_and_unrepresentable_facts_become_findings(self):
        analysis = self.analyse()

        self.assertEqual((analysis.facts["F2"].outcome, analysis.facts["F2"].basis), ("mapped", "lexical"))
        self.assertEqual(analysis.facts["F1"].outcome, "unmapped")
        messages = [f.message for f in analysis.findings]
        self.assertIn("Not represented in the model: City = Auckland (Eden Park)", messages)
        self.assertIn("Not represented in the model: Use = Opening match and final (Eden Park)", messages)

    def test_the_unmentioned_sponsor_is_never_touched(self):
        change_set, _ = self.compile(self.analyse())

        self.assertNotIn("acme_corp", change_set.model_dump_json())

    def test_esc_selects_and_never_adds_evidence(self):
        analysis = self.analyse()

        self.assertEqual(analysis.graph.ids(), self.rs.graph.ids())
        self.assertLessEqual(analysis.scope.selected_assertions, {a.aid for a in self.rs.graph.assertions})


class MappingTests(PipelineTestCase):
    text = NOTES

    def items(self, *extra):
        return [
            entity("E3", "Match 1", "match", hint="match", excerpt="Match 1"),
            entity("E6", "Eden Park", "venue", hint="venue", excerpt="Eden Park"),
            *extra,
        ]

    def stage_frame(self):
        return frame([target("T2", "stages", "stages")])

    def test_a_hint_legal_only_in_the_converse_is_never_reversed_silently(self):
        analysis = self.analyse(self.items(assertion("A1", "E6", "hosts", "E3", hint="played_at", excerpt="Eden Park hosts Match 1")), intent_frame=self.stage_frame())

        mapping = analysis.assertions["A1"]
        self.assertEqual(mapping.outcome, "ambiguous")
        self.assertEqual(mapping.options, ["played_at:converse"])

    def test_an_explicit_converse_claim_is_accepted(self):
        analysis = self.analyse(self.items(assertion("A1", "E6", "hosts", "E3", hint="played_at", orientation="converse", excerpt="Eden Park hosts Match 1")),
                                intent_frame=self.stage_frame())

        mapping = analysis.assertions["A1"]
        self.assertEqual((mapping.outcome, mapping.basis, mapping.orientation), ("mapped", "hint", "converse"))
        self.assertEqual((mapping.canonical_subject, mapping.canonical_object), ("E3", "E6"))

    def test_same_type_rules_are_flagged_orientation_unverifiable(self):
        rival = self.make_relationship_type(self.model, key="rival_of")
        self.make_rule(rival, self.team_type, self.team_type)
        items = [entity("E4", "New Zealand", "team", hint="team"), entity("E5", "Fiji", "team", hint="team"),
                 assertion("A1", "E4", "is a rival of", "E5", hint="rival_of", excerpt="New Zealand is a rival of Fiji")]

        analysis = self.analyse(items, intent_frame=self.stage_frame())

        self.assertEqual(analysis.assertions["A1"].outcome, "mapped")
        self.assertIn("orientation_unverifiable", analysis.ledger.get("map:A1").flags)

    def test_several_plausible_relationship_types_are_ambiguous_then_unresolved_never_unmapped(self):
        rehearsed = self.make_relationship_type(self.model, key="rehearsed_at")
        self.make_rule(rehearsed, self.match_type, self.venue_type)
        stage = entity("E2", "Pool Stage", "stage", hint="stage", excerpt="Pool Stage")
        items = self.items(stage, assertion("A0", "E2", "includes", "E3", hint="has_match", excerpt="Pool Stage includes Match 1"),
                           assertion("A1", "E3", "was staged at", "E6", excerpt="Match 1 was staged at Eden Park"))

        analysis = self.analyse(items, intent_frame=self.stage_frame())
        self.assertEqual(analysis.assertions["A1"].outcome, "ambiguous")
        self.assertEqual(set(analysis.assertions["A1"].options), {"played_at:as_stated", "rehearsed_at:as_stated"})
        # Asked once per wording-and-kinds pattern, so a table's rows share one answer.
        pattern = "predicate_mapping:was_staged_at:match:venue"
        self.assertIn(pattern, [question.question_id for question in analysis.questions])
        by_pattern = self.analyse(items, intent_frame=self.stage_frame(), pins={pattern: self.pin("played_at:as_stated")})
        self.assertEqual(by_pattern.assertions["A1"].outcome, "mapped")

        undecided = self.analyse(items, intent_frame=self.stage_frame(), pins={q.key("assertion_mapping", "A1"): self.pin(q.UNDECIDABLE)})
        self.assertEqual(undecided.assertions["A1"].outcome, "unresolved_ambiguity")

        chosen = self.analyse(items, intent_frame=self.stage_frame(), pins={q.key("assertion_mapping", "A1"): self.pin("played_at:as_stated")})
        self.assertEqual((chosen.assertions["A1"].outcome, chosen.assertions["A1"].basis), ("mapped", "adjudicated"))
        self.assertIn(q.pin_decision_id(q.key("assertion_mapping", "A1")), chosen.ledger.get("map:A1").inputs)

    def test_an_untyped_entity_is_ambiguous_not_dropped(self):
        analysis = self.analyse([entity("E1", "Eden Park", "ground")], intent_frame=frame())

        self.assertEqual(analysis.types["E1"].outcome, "ambiguous")


class IdentityTests(PipelineTestCase):

    def test_a_unique_exact_match_is_a_lexical_identity(self):
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park")

        analysis = self.analyse()

        identity = analysis.identities[self.cid(analysis, "Eden Park")]
        self.assertEqual((identity.outcome, identity.basis), ("existing", "lexical"))
        self.assertIn("lexical_identity", analysis.ledger.get(identity.decision_id).flags)

    def test_two_name_matches_are_ambiguous(self):
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park")
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park_2")

        analysis = self.analyse()

        identity = analysis.identities[self.cid(analysis, "Eden Park")]
        self.assertEqual(identity.outcome, "ambiguous")
        self.assertEqual(set(identity.options), {"eden_park", "eden_park_2", q.NEW})
        self.assertIn(q.key("identity", self.cid(analysis, "Eden Park")), [question.question_id for question in analysis.questions])

    def test_a_retired_match_is_reactivated_not_duplicated(self):
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park", is_active=False)

        analysis = self.analyse()
        change_set, trace = self.compile(analysis)

        self.assertEqual(analysis.identities[self.cid(analysis, "Eden Park")].outcome, "reactivate")
        self.assertTrue(any(a.kind == "set_active" and a.active for a in change_set.actions))
        self.assertFalse(any(a.kind == "create_object" and a.name == "Eden Park" for a in change_set.actions))
        self.assertEqual(check_trace(change_set, trace, analysis), [])


class IndirectTests(PipelineTestCase):
    text = NOTES

    def direct_stage_venue(self):
        return [
            entity("E2", "Pool Stage", "stage", hint="stage", excerpt="Pool Stage"),
            entity("E7", "Forsyth Barr Stadium", "venue", hint="venue", excerpt="Forsyth Barr Stadium"),
            assertion("A1", "E2", "is held at", "E7", excerpt="Pool Stage is held at Forsyth Barr Stadium"),
        ]

    def test_an_indirect_path_is_not_asked_about_nor_classified_by_onyxjar(self):
        analysis = self.analyse(self.direct_stage_venue())

        decision = analysis.ledger.get("map:A1")
        self.assertEqual((decision.outcome, decision.reason), ("indirect", "indirect_unclassified"))
        self.assertEqual(decision.mapping["paths"][0]["via_type"], "match")
        self.assertEqual(decision.question_key, q.key("indirect_classification", "A1"))  # still a reviewer's target
        self.assertNotIn(q.key("indirect_classification", "A1"), [question.question_id for question in analysis.questions])

    def test_no_answer_to_an_indirect_path_changes_what_is_decided(self):
        """Why it is never asked: every possible answer leaves scope,
        viability, blocked causes and the compiled changes exactly as no
        answer does. If this fails, the answer has become material -- ask
        it again (ai.services.reconcile.analysis._questions)."""

        key = q.key("indirect_classification", "A1")
        index = SemanticModelIndex.load(self.model)

        def decided(pins):
            analysis = self.analyse(self.direct_stage_venue(), pins=pins)
            change_set, _ = self.compile(analysis)
            requirements = {
                r.requirement_id: (r.evidenced, r.viable_count, list(r.pending_decision), list(r.candidates))
                for rs in analysis.scope.requirements.values() for r in rs
            }
            return {
                "outcomes": dict(analysis.scope.outcomes),
                "selected": sorted(analysis.scope.selected_assertions),
                "viable": sorted(analysis.scope.viable),
                "requirements": requirements,
                "blocked": analysis.blocked_targets(index, {}),
                "questions": sorted(question.question_id for question in analysis.questions),
                "actions": [a.model_dump(mode="json") for a in change_set.actions],
            }

        unanswered = decided({})
        for option in ("refers_to_intermediate", "direct_statement", q.UNDECIDABLE, q.NONE):
            self.assertEqual(decided({key: self.pin(option)}), unanswered, option)

    def test_an_adjudicated_direct_statement_is_no_direct_representation_and_never_compiled(self):
        analysis = self.analyse(self.direct_stage_venue(), pins={q.key("indirect_classification", "A1"): self.pin("direct_statement")})

        self.assertEqual(analysis.ledger.get("map:A1").reason, "no_direct_representation")
        self.assertNotIn("A1", analysis.scope.selected_assertions)

    def test_an_immaterial_path_stays_unclassified_without_a_question(self):
        items = [
            entity("E4", "New Zealand", "team", hint="team"),
            entity("E6", "Eden Park", "venue", hint="venue", excerpt="Eden Park"),
            assertion("A1", "E4", "plays at", "E6", excerpt="New Zealand plays at Eden Park"),
        ]

        analysis = self.analyse(items, intent_frame=frame([target("T2", "stages", "stages")]))

        self.assertEqual(analysis.ledger.get("map:A1").reason, "indirect_unclassified")
        self.assertEqual(analysis.questions, [])


class ObservationTests(PipelineTestCase):
    text = NOTES

    def eden(self, *facts):
        return [entity("E6", "Eden Park", "venue", hint="venue", excerpt="Eden Park"), *facts]

    def capacity_set(self, analysis):
        return analysis.attribute_sets[("E6", "capacity")]

    def test_differently_qualified_values_are_distinct_not_a_conflict(self):
        analysis = self.analyse(self.eden(
            fact("F1", "E6", "Capacity", "50000", excerpt="Eden Park capacity: 50000 as of 2027", as_of="2027"),
            fact("F2", "E6", "Seating", "42000", excerpt="Eden Park seating: 42000 in 2019", as_of="2019"),
        ), pins={q.key("fact_attribute", "F2"): self.pin("capacity")})

        self.assertEqual(self.capacity_set(analysis).classification, "distinct")
        self.assertIn(q.key("value_selection", "E6:capacity"), [question.question_id for question in analysis.questions])

    def test_an_explicit_correction_supersedes(self):
        analysis = self.analyse(self.eden(
            fact("F1", "E6", "Capacity", "48000", excerpt="Eden Park capacity: 48000"),
            fact("F2", "E6", "Capacity", "50000", excerpt="Eden Park capacity was corrected to 50000",
                 supersedes={"target_fid": "F1", "excerpt": "corrected to 50000"}),
        ))

        self.assertEqual(self.capacity_set(analysis).classification, "superseded")
        self.assertEqual([(v.attribute_key, v.value) for v in analysis.values], [("capacity", 50000)])

    def test_an_unqualified_contradiction_is_never_resolved_by_onyxjar(self):
        items = self.eden(
            fact("F1", "E6", "Capacity", "48000", excerpt="Eden Park capacity: 48000"),
            fact("F2", "E6", "Capacity", "50000", excerpt="Eden Park capacity: 50000 as of 2027"),
        )

        analysis = self.analyse(items)
        self.assertEqual(self.capacity_set(analysis).classification, "candidate_conflict")
        question = next(question for question in analysis.questions if question.kind == "conflict_classification")
        self.assertEqual(question.option_ids(), {"contradictory", "distinct", q.UNDECIDABLE})

        settled = self.analyse(items, pins={question.question_id: self.pin("contradictory")})
        self.assertEqual(self.capacity_set(settled).classification, "conflict")
        self.assertEqual(settled.values, [])
        change_set, trace = self.compile(settled)
        eden = next(a for a in change_set.actions if a.kind == "create_object" and a.name == "Eden Park")
        self.assertEqual(eden.attributes, [])
        self.assertTrue(any("Conflicting evidence for capacity" in f.message for f in settled.findings))


class PartialOutcomeTests(PipelineTestCase):

    def without_fiji(self, **state):
        return self.analyse(self.flyer_items(include_fiji=False), **state)

    def test_an_unsatisfied_requirement_is_probed_not_invented(self):
        analysis = self.without_fiji()

        self.assertEqual([r.requirement_id.split(":")[1] for r in analysis.probe_requests], ["E3"])
        self.assertFalse(any(e.name == "Fiji" for e in analysis.graph.entities))

    def test_a_blocked_target_leaves_independent_targets_compilable(self):
        requirement = self.without_fiji().probe_requests[0].requirement_id
        analysis = self.without_fiji(probed={requirement}, probe_outcomes={requirement: "not_stated"}, missing_evidence={requirement: "complete"})

        self.assertEqual(self.outcome(analysis, "Pool Stage"), "blocked")
        self.assertEqual(self.outcome(analysis, "Match 1"), "blocked_dependent")
        self.assertEqual(self.outcome(analysis, "New Zealand"), "blocked_dependent")
        self.assertEqual(self.outcome(analysis, "Eden Park"), "selected")
        self.assertEqual(self.outcome(analysis, "Forsyth Barr Stadium"), "selected")

        blocked = analysis.blocked_targets(SemanticModelIndex.load(self.model), self.rs.missing_evidence)
        self.assertEqual([b["target"] for b in blocked], ["Pool Stage"])
        self.assertEqual(set(blocked[0]["dependants"]), {"Match 1", "New Zealand"})
        self.assertTrue(any(m.get("entity") == "Match 1" and m["relationship_type_key"] == "has_team" and m["found"] == 1 for m in blocked[0]["missing_requirements"]))

        change_set, trace = self.compile(analysis)
        self.assertEqual(sorted(a.name for a in change_set.actions), ["Eden Park", "Forsyth Barr Stadium"])
        self.assertEqual(check_trace(change_set, trace, analysis), [])


class TraceAndRemovalTests(PipelineTestCase):

    def test_a_structural_decision_resting_on_nothing_is_an_i2_violation(self):
        ledger = Ledger()
        ledger.claim("E1", step="extraction", basis="extraction")
        ledger.structural("type:E1", step="mapping", inputs=["E1"], outcome="mapped")
        ledger.structural("invented", step="scope", inputs=["nothing"], outcome="selected")

        self.assertEqual(ledger.i2_violations(), ["invented"])

    def test_trace_policy_rejects_an_untraced_relationship(self):
        analysis = self.analyse()
        change_set, trace = self.compile(analysis)
        action = next(a for a in change_set.actions if a.kind == "create_relationship")
        trace.entries[action.action_id].decision_ids = [d for d in trace.entries[action.action_id].decision_ids if not d.startswith("map:")]

        issues = check_trace(change_set, trace, analysis)

        self.assertTrue(any(i.action_id == action.action_id and i.code == "trace_violation" for i in issues))

    def test_retirement_needs_an_explicit_confirmed_removal_claim(self):
        self.text = NOTES
        items = [entity("E9", "Acme Corp", "sponsor", hint="sponsor", polarity="removed", excerpt="Acme Corp no longer sponsors the championship")]
        sponsor_frame = frame([target("T1", "sponsors", "venues", verb="retire", hint="sponsor")])

        unconfirmed = self.analyse(items, intent_frame=sponsor_frame)
        self.assertEqual([question.kind for question in unconfirmed.questions], ["removal_confirmation"])
        self.assertEqual(self.compile(unconfirmed)[0].actions, [])

        confirmed = self.analyse(items, intent_frame=sponsor_frame, pins={q.key("removal_confirmation", "E9"): self.pin("confirm")})
        change_set, trace = self.compile(confirmed)
        self.assertEqual([(a.kind, a.active) for a in change_set.actions], [("set_active", False)])
        self.assertEqual(check_trace(change_set, trace, confirmed), [])

    def test_absence_from_the_evidence_is_never_removal(self):
        change_set, _ = self.compile(self.analyse())

        self.assertFalse(any(a.kind == "set_active" and not a.active for a in change_set.actions))

    def test_empty_evidence_compiles_nothing(self):
        analysis = self.analyse([], intent_frame=frame())

        self.assertEqual(self.compile(analysis)[0].actions, [])
        self.assertIsInstance(self.rs.graph, EvidenceGraph)
