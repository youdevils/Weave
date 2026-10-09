"""
The deterministic governance core as a contract (Phase 0 of
.Documentation/reconcile-architecture-plan.md).

Given IDEAL semantic input -- the claims a perfect reader of the
international rugby flyer would make, each citing the real segment of the
real PDF that states it -- the deterministic core (ingress-independent
analysis -> ESC -> compile -> TracePolicy -> resolution -> speculative
staging) must reach the reference outcome in
ai/tests/fixtures/references/international_flyer.json, and must keep its
negative guarantees whatever else the input contains.

No provider is involved: anything that fails here is a governance defect,
not an interpretation defect. The ontology is the live "International Rugby
Tournament" catalogue the captured flyer runs used.
"""

from ai.services.artifacts import Provenance
from ai.services.evidence_bundle import EvidenceBundle
from ai.services.evidence_graph import EvidenceAssertion, EvidenceEntity, validate_evidence_graph
from ai.services.grounding import STRUCTURAL, UNANCHORED, ground_graph
from ai.tests.reference import assert_reference, load_spec, norm, run_core
from ai.tests.support import AIServiceTestCase, frame, graph, target
from ai.tests.test_evidence_lifecycle import flyer_assets

INTENT = ("I want add the venues and stages listed in the flyer to my model, create any relationships that should be "
          "associated as well based on the information available")

TITLE = "PACIFIC INTERNATIONAL RUGBY CHAMPIONSHIP 2027"

# (eid, name, type key, segment it is named in)
TEAMS = [("NZ", "New Zealand", "S1#t1.r1"), ("FJ", "Fiji", "S1#t1.r1"), ("JP", "Japan", "S1#t1.r1"), ("WS", "Samoa", "S1#t1.r1"),
         ("AU", "Australia", "S1#t1.r2"), ("AR", "Argentina", "S1#t1.r2"), ("ZA", "South Africa", "S1#t1.r2"), ("TO", "Tonga", "S1#t1.r2")]
VENUES = [("V1", "Eden Park", "S1#t2.r1"), ("V2", "Sky Stadium", "S1#t2.r2"), ("V3", "Forsyth Barr Stadium", "S1#t2.r3"),
          ("V4", "FMG Stadium Waikato", "S1#t2.r4"), ("V5", "McLean Park", "S1#t2.r5"), ("V6", "Orangetheory Stadium", "S1#t2.r6")]
STAGES = [("PA", "Pool A", "S1#t3.r1"), ("PB", "Pool B", "S1#t3.r3"), ("QF", "Quarter-finals", "S1#8"),
          ("SF", "Semi-finals", "S1#9"), ("FI", "Final", "S1#10")]
# (eid, name, stage eid, venue eid, team eids, fixture row)
MATCHES = [("M1", "New Zealand v Fiji", "PA", "V1", ("NZ", "FJ"), "S1#t3.r1"),
           ("M2", "Japan v Samoa", "PA", "V2", ("JP", "WS"), "S1#t3.r2"),
           ("M3", "Australia v Argentina", "PB", "V3", ("AU", "AR"), "S1#t3.r3"),
           ("M4", "South Africa v Tonga", "PB", "V4", ("ZA", "TO"), "S1#t3.r4"),
           # The quarter-final fixtures: specific matches whose participants the
           # source does not identify -- no team is ever claimed for them.
           ("Q1", "Pool A winner v Pool B runner-up", "QF", "V6", (), "S1#t4.r1"),
           ("Q2", "Pool B winner v Pool A runner-up", "QF", "V2", (), "S1#t4.r2")]


def cite(segment_id, excerpt, source_id="S1"):
    return Provenance(source_id=source_id, excerpt=excerpt, segment_id=segment_id)


def ent(eid, name, type_key, segment_id, *, specificity="specific"):
    return EvidenceEntity(eid=eid, name=name, type_label=type_key, type_hint=type_key, specificity=specificity,
                          provenance=[cite(segment_id, name)])


def rel(aid, subject, predicate, obj, hint, citations, *, support="explicit"):
    return EvidenceAssertion(aid=aid, subject_eid=subject, predicate=predicate, object_eid=obj, relationship_type_hint=hint,
                             support=support, provenance=citations)


class GovernanceContractTestCase(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model(name="International Rugby Tournament")
        types = {k: self.make_object_type(self.model, key=k) for k in ("tournament", "stage", "match", "team", "venue")}
        names = {"has_stage": "has stage", "has_match": "has match", "has_team": "has team", "has_team_2": "has team",
                 "played_at": "played at"}
        rel_types = {k: self.make_relationship_type(self.model, key=k, name=n) for k, n in names.items()}
        # Exactly the captured live catalogue (trace 24063e61).
        self.make_rule(rel_types["has_match"], types["stage"], types["match"], object_minimum=1, subject_minimum=1)
        self.make_rule(rel_types["has_stage"], types["tournament"], types["stage"], object_minimum=1, subject_minimum=1, subject_maximum=1)
        self.make_rule(rel_types["has_team"], types["match"], types["team"], object_minimum=2, object_maximum=2,
                       subject_minimum=1, subject_maximum=1)
        self.make_rule(rel_types["has_team_2"], types["tournament"], types["team"], object_minimum=2, subject_minimum=1, subject_maximum=1)
        self.make_rule(rel_types["played_at"], types["match"], types["venue"], object_minimum=1, subject_minimum=1)
        self.assets = flyer_assets()

    # -- ideal semantic input -----------------------------------------------------

    def text(self, segment_id):
        return self.bundle().segment(segment_id).text

    def bundle(self, extra_assets=()):
        return EvidenceBundle.from_assets([*self.assets, *extra_assets])

    def ideal_items(self, *, team_participation=True, structural_participation=True):
        title = cite("S1#1", TITLE)
        items = [ent("T", TITLE, "tournament", "S1#1")]
        items += [ent(eid, name, "stage", seg) for eid, name, seg in STAGES]
        items += [rel(f"HS_{eid}", "T", "has stage", eid, "has_stage", [title, cite(seg, self.text(seg))], support="structural")
                  for eid, _, seg in STAGES]
        items += [ent(eid, name, "venue", seg) for eid, name, seg in VENUES]
        items += [ent(eid, name, "team", seg) for eid, name, seg in TEAMS]
        if team_participation:
            for eid, _, seg in TEAMS:
                citations = [title, cite(seg, self.text(seg))]
                items.append(rel(f"HT2_{eid}", "T", "has team", eid, "has_team_2", citations,
                                 support="structural" if structural_participation else "explicit"))
        for eid, name, stage, venue, teams, row in MATCHES:
            row_cite = [cite(row, self.text(row))]
            items.append(ent(eid, name, "match", row))
            items.append(rel(f"HM_{eid}", stage, "has match", eid, "has_match", row_cite))
            items.append(rel(f"PL_{eid}", eid, "played at", venue, "played_at", row_cite))
            items += [rel(f"HT_{eid}_{team}", eid, "has team", team, "has_team", row_cite) for team in teams]
        return items

    def frame(self):
        excerpt = "add the venues and stages listed in the flyer"
        return frame([target("T1", "venues", excerpt, hint="venue"), target("T2", "stages", excerpt, hint="stage")],
                     include_related=True, include_related_excerpt="create any relationships that should be associated")

    # -- the deterministic core, end to end ---------------------------------------

    def analyse(self, items, *, extra_assets=()):
        """The core run on these claims (ai.tests.reference.run_core); returns
        its final analysis, keeping the rest for `govern`."""

        self.core = run_core(self, model=self.model, frame=self.frame(), items=items,
                             assets=[*self.assets, *extra_assets], intent=INTENT)
        return self.core.analysis

    def govern(self, analysis):
        """What compile -> TracePolicy -> resolution -> staging produced for
        the last `analyse` (run_core asserts each step's guarantees)."""

        self.assertIs(analysis, self.core.analysis)
        return self.core.change_set, self.core.blocked, self.core.outcome

    def cid(self, analysis, name):
        return next(c for c, cluster in analysis.clusters.clusters.items() if cluster.name == name)

    def outcome_of(self, analysis, name):
        return analysis.scope.outcomes.get(self.cid(analysis, name))


class ReferenceOutcomeTests(GovernanceContractTestCase):

    def test_ideal_semantic_input_reaches_the_reference_outcome(self):
        analysis = self.analyse(self.ideal_items())
        _, _, outcome = self.govern(analysis)

        assert_reference(self, outcome, load_spec("international_flyer"))

    def test_the_ideal_input_is_entirely_grounded(self):
        bundle = self.bundle()
        items = graph(*self.ideal_items())

        self.assertEqual(validate_evidence_graph(items, bundle=bundle, intent_text=INTENT), [])
        self.assertNotIn(UNANCHORED, ground_graph(items, bundle=bundle).values())


class NegativeGuaranteeTests(GovernanceContractTestCase):

    def test_quarter_finals_stay_blocked_although_their_related_entities_compile(self):
        analysis = self.analyse(self.ideal_items())
        _, _, outcome = self.govern(analysis)

        for name in ("Quarter-finals", "Pool A winner v Pool B runner-up", "Pool B winner v Pool A runner-up", "Orangetheory Stadium"):
            self.assertNotIn(norm(name), outcome.names_of(), name)
        # Related entities exist and compile: the venue a QF match is played
        # at, and the tournament the stage belongs to.
        self.assertIn(norm("Sky Stadium"), outcome.names_of("venue"))
        self.assertIn(norm(TITLE), outcome.names_of("tournament"))
        self.assertEqual(outcome.blocked[norm("Quarter-finals")], "insufficient_evidence")

    def test_mclean_park_is_never_evidenced_by_appearing_in_the_source(self):
        items = self.ideal_items()
        # A claim citing a segment that names McLean Park but not the match
        # (unanchored), and the venue table's generic "Pool matches" (a real,
        # anchored statement about unidentified matches).
        items.append(rel("BAD", "Q1", "played at", "V5", "played_at", [cite("S1#t2.r5", self.text("S1#t2.r5"))]))
        items.append(ent("GM", "Pool matches", "match", "S1#t2.r5", specificity="generic"))
        items.append(rel("GEN", "GM", "played at", "V5", "played_at", [cite("S1#t2.r5", self.text("S1#t2.r5"))]))
        analysis = self.analyse(items)
        _, _, outcome = self.govern(analysis)

        self.assertNotIn(norm("McLean Park"), outcome.names_of())
        self.assertFalse(any(o == norm("McLean Park") for t, _, o in outcome.relationships if t == "played_at"))
        self.assertNotIn("BAD", analysis.scope.selected_assertions)
        self.assertNotIn("GEN", analysis.scope.selected_assertions)
        assert_reference(self, outcome, load_spec("international_flyer"))

    def test_structural_evidence_satisfies_the_requirement_it_states(self):
        items = self.ideal_items()
        analysis = self.analyse(items)

        grounding = ground_graph(graph(*items), bundle=self.bundle())
        self.assertEqual({grounding[f"HT2_{eid}"] for eid, _, _ in TEAMS}, {STRUCTURAL})
        self.assertTrue({f"HT2_{eid}" for eid, _, _ in TEAMS} <= analysis.scope.selected_assertions)
        self.assertEqual(self.outcome_of(analysis, TITLE), "selected")

    def test_invalid_claims_stay_rejected(self):
        bundle = self.bundle()
        row = cite("S1#t2.r1", self.text("S1#t2.r1"))
        defective = graph(
            ent("V1", "Eden Park", "venue", "S1#t2.r1"),
            rel("SELF", "V1", "Opening match and final", "V1", None, [row]),
            rel("NOEND", "V1", "hosts", "", None, [row]),
        )
        codes = {(i.item_id, i.code) for i in validate_evidence_graph(defective, bundle=bundle, intent_text=INTENT)}
        self.assertIn(("SELF", "self_reference"), codes)
        self.assertIn(("NOEND", "missing_endpoint"), codes)

        # The same participation claims, but without structural support: one
        # explicit citation set naming each side in different segments is
        # not anchored, so it can satisfy nothing -- and everything that
        # depends on the tournament's teams is blocked rather than invented.
        analysis = self.analyse(self.ideal_items(structural_participation=False))
        self.assertTrue(all(analysis.grounding.get(f"HT2_{eid}") == UNANCHORED for eid, _, _ in TEAMS))
        change_set, _, outcome = self.govern(analysis)
        self.assertFalse(any(t == "has_team_2" for t, _, _ in outcome.relationships))
        self.assertNotIn(norm(TITLE), outcome.names_of())

    def test_cardinality_stays_authoritative(self):
        extra = [{"name": "addendum.txt", "content": "Addendum: New Zealand v Fiji also featured Japan.", "mime_type": "text/plain"}]
        items = self.ideal_items()
        items.append(rel("THIRD", "M1", "also featured", "JP", "has_team", [cite("S2#1", "New Zealand v Fiji also featured Japan", "S2")]))
        analysis = self.analyse(items, extra_assets=extra)
        _, _, outcome = self.govern(analysis)

        self.assertTrue(analysis.scope.constraint_conflicts, "three simultaneous teams on a two-team match is a conflict")
        self.assertNotIn(norm("New Zealand v Fiji"), outcome.names_of("match"))
        self.assertFalse(any(s == norm("New Zealand v Fiji") for t, s, _ in outcome.relationships if t == "has_team"))

    def test_a_missing_upstream_requirement_blocks_the_whole_cascade(self):
        analysis = self.analyse(self.ideal_items(team_participation=False))
        change_set, blocked, outcome = self.govern(analysis)

        self.assertEqual(change_set.actions, [])
        eden = next(b for b in blocked if b["target"] == "Eden Park")
        chain = eden["cascade"]["chain"]
        self.assertEqual(chain[:2], ["Eden Park", "New Zealand v Fiji"])
        self.assertIn(chain[-1], {"New Zealand", "Fiji"})
        cause = eden["cascade"]["cause"]
        self.assertEqual((cause["relationship_type_key"], cause["counterpart_type_key"]), ("has_team_2", "tournament"))

    def test_document_structure_alone_manufactures_nothing(self):
        analysis = self.analyse([])
        change_set, _, outcome = self.govern(analysis)

        self.assertEqual(change_set.actions, [])
        self.assertEqual(outcome.objects, set())
        self.assertEqual(analysis.scope.selected_assertions, set())
        self.assertEqual(analysis.ledger.i2_violations(), [])
        # The intent frame is a claim about the request; about the evidence there is none.
        self.assertFalse([d for d in analysis.ledger.payload() if d["kind"] == "claim" and d["step"] != "framing"])
