"""
The first successful UI run of the Readings architecture (execution
ffda0076-aaec-4703-8994-72fb9bdfdc50: the international flyer, "add the venues
and stages ...", gpt-4.1, 12 provider calls), replayed under
`EquivalenceReplay` on the live model (`LateRoundFixture`, same rule ids).

Two layers:

- OUTCOME invariants (`FirstReadingsRunOutcomeTests`) -- what the run decided.
  They must hold whatever the workflow's efficiency: a change that alters
  any of them changes what the run decides, which is never a side effect.
- PATH observations (`FirstReadingsRunPathTests`) -- the calls the captured
  run made. A later change may legitimately make fewer (e.g. a Reading
  correction no longer needed); it may not make a call the captured run did
  not, nor reorder them.

The fixture is ai/tests/fixtures/traces/international_flyer_readings_ffda0076
(capture_reconcile_fixture of the raw trace).
"""

from pathlib import Path

from django.test import override_settings

from ai.services.result_schema import OperationOutcome
from ai.services.tracing import load
from ai.tests.reference import assert_reference, blocked_state, load_spec, norm, outcome_from_proposal
from ai.tests.test_trace_equivalence import FlyerReplayCase

RUN = "readings_ffda0076"
TITLE = "pacific international rugby championship 2027"
TEAMS = ("new zealand", "fiji", "japan", "samoa", "australia", "argentina", "south africa", "tonga")
MATCHES = {
    "new zealand v fiji": ("pool a", "eden park"),
    "japan v samoa": ("pool a", "sky stadium"),
    "australia v argentina": ("pool b", "forsyth barr stadium"),
    "south africa v tonga": ("pool b", "fmg stadium waikato"),
}

OBJECTS = {
    ("tournament", TITLE), ("stage", "pool a"), ("stage", "pool b"),
    *(("team", t) for t in TEAMS), *(("match", m) for m in MATCHES),
    *(("venue", v) for _, v in MATCHES.values()),
}
RELATIONSHIPS = {
    ("has_stage", TITLE, "pool a"), ("has_stage", TITLE, "pool b"),
    *(("has_team_2", TITLE, t) for t in TEAMS),
    *(("has_match", stage, m) for m, (stage, _) in MATCHES.items()),
    *(("played_at", m, venue) for m, (_, venue) in MATCHES.items()),
    *(("has_team", m, team) for m in MATCHES for team in m.split(" v ")),
}
BLOCKED = {
    "Pool Stage": "not_stated",
    "Quarter-final": "insufficient_evidence",
    "Semi-finals": "not_stated",
    "Final": "not_stated",
    "McLean Park": "not_stated",
    "Orangetheory Stadium": "insufficient_evidence",
}
# Adjudication: the tournament's links to the tables under its heading (the
# Teams-table has_team_2 answers above all -- the answer earlier live runs got
# wrong), and the prose Quarter-finals as the fixture table's stage.
PINS = {
    "reading_slot:rd/S1#1/section_relation/S1#t1.c1": "has_stage:as_stated",
    "reading_slot:rd/S1#1/section_relation/S1#t3.c1": "has_stage:as_stated",
    "reading_slot:rd/S1#1/section_relation/S1#t4.c1": "has_stage:as_stated",
    "reading_slot:rd/S1#1/section_relation/S1#t1.c2": "has_team_2:as_stated",
    "reading_slot:rd/S1#1/section_relation/S1#t1.c3": "has_team_2:as_stated",
    "reading_slot:rd/S1#1/section_relation/S1#t1.c4": "has_team_2:as_stated",
    "reading_slot:rd/S1#1/section_relation/S1#t1.c5": "has_team_2:as_stated",
    "coreference:E2:x/S1#t4.r1.c1": "same",
    "coreference:E2:x/S1#t4.r2.c1": "same",
}
# The only pin a later change has added: probe claims about Reading-expanded
# entities are no longer dropped as dangling, so the round-2 correction's
# structural "tournament has stage Pool Stage / Semi-finals / Final" claims
# are accepted and their predicate is mapped by Adjudication (here answered
# by the replay's single-option stand-in -- the captured run never got it).
ADDED_PINS = {"predicate_mapping:has_stage:tournament:stage": "has_stage:as_stated"}
RECOVERED_STAGES = ("Pool Stage", "Semi-finals", "Final")
# The Reading related the Pool column to the team columns by has_team_2,
# which is tournament -> team only: illegal between stage and team.
ILLEGAL_SLOTS = [f"rd/S1#t1/relation/c1>c{n}" for n in range(2, 6)]
CAPTURED_PATH = [
    "reading", "reading", "reading", "reading", "extraction", "extraction_correction", "adjudication",
    "gap_probe", "gap_probe_correction", "gap_probe", "gap_probe_correction", "verification",
]
# What the captured path has become: + the Adjudication round for ADDED_PINS.
PATH = [*CAPTURED_PATH[:-1], "adjudication", "verification"]


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings")
class FirstReadingsRunCase(FlyerReplayCase):
    maxDiff = None

    def replay_run(self):
        provider, result = self.replay(RUN)
        steps = load(Path(self.trace_dir.name) / str(result.execution_id))
        snapshot = [s["snapshot"] for s in steps if s["kind"] == "deterministic"][-1]
        return provider, result, snapshot


class FirstReadingsRunOutcomeTests(FirstReadingsRunCase):

    def setUp(self):
        super().setUp()
        self.provider, self.result, self.snapshot = self.replay_run()
        self.outcome = outcome_from_proposal(self.result.proposal_id, self.result.blocked_targets)

    def test_ready_for_review_and_partial(self):
        self.assertEqual(self.result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(self.result.completeness, "partial")
        self.assertEqual(self.provider.unaligned, [])

    def test_the_reference_spec_passes(self):
        assert_reference(self, self.outcome, load_spec("international_flyer"))

    def test_exactly_the_captured_objects_and_relationships(self):
        self.assertEqual(self.outcome.objects, OBJECTS)
        self.assertEqual(len(self.outcome.objects), 19)
        self.assertEqual(self.outcome.relationships, RELATIONSHIPS)
        self.assertEqual(len(self.outcome.relationships), 26)

    def test_the_blocked_state_map(self):
        self.assertEqual({b["target"]: blocked_state(b) for b in self.result.blocked_targets}, BLOCKED)

    def test_the_nine_adjudication_pins(self):
        pins = {k: v["option_id"] for k, v in self.snapshot["pins"].items()}

        self.assertEqual({k: pins.get(k) for k in PINS}, PINS)
        self.assertEqual({k: v for k, v in pins.items() if k not in PINS}, ADDED_PINS)

    def test_probe_claims_about_the_title_entity_are_kept(self):
        # Their stages still need a match, so they stay blocked as not_stated;
        # what changes is that the has_stage the evidence states is no longer
        # reported missing, nor the claims as "not extracted".
        blocked = {b["target"]: b for b in self.result.blocked_targets}
        for stage in RECOVERED_STAGES:
            with self.subTest(stage=stage):
                self.assertEqual({m["relationship_type_key"] for m in blocked[stage]["missing_requirements"]}, {"has_match"})
        self.assertFalse([f.message for f in self.result.findings if "was not extracted" in f.message])

    def test_illegal_has_team_2_column_relations_are_rejected_and_never_compiled(self):
        reading = next(r for r in self.snapshot["readings"] if r["element_id"] == "S1#t1")
        slots = {s["slot_id"]: s for s in reading["slots"]}
        for slot_id in ILLEGAL_SLOTS:
            with self.subTest(slot=slot_id):
                self.assertEqual((slots[slot_id]["choice"], slots[slot_id]["state"]), ("has_team_2:as_stated", "rejected"))
        self.assertFalse([r for r in self.outcome.relationships if r[0] == "has_team_2" and r[1] != TITLE])

    def test_placeholder_participants_never_become_objects(self):
        self.assertFalse([n for _, n in self.outcome.objects if any(w in n for w in ("winner", "runner-up", "runner up"))])
        self.assertNotIn(norm("Quarter-final"), self.outcome.names_of())


class FirstReadingsRunPathTests(FirstReadingsRunCase):
    """Observations, not invariants: the captured run's calls."""

    def test_no_call_beyond_the_known_path(self):
        provider, result, _ = self.replay_run()
        self.report(RUN, {"requested": provider.requested, "stage_summary": result.stage_summary})

        remaining = iter(PATH)
        self.assertTrue(all(stage in remaining for stage in provider.requested),
                        f"{provider.requested} is not the known path {PATH} less some calls")
        self.assertLessEqual(result.provider_calls, len(PATH))

    def test_the_path_as_of_now(self):
        # Update deliberately when a change removes or adds calls (and say which).
        provider, result, _ = self.replay_run()

        self.assertEqual(provider.requested, PATH)
        corrections = {stage: summary["corrections"] for stage, summary in result.stage_summary.items() if summary["corrections"]}
        self.assertEqual(corrections, {"reading": 2})
        self.assertEqual(result.stage_summary.get("reading_correction"), {"calls": 2, "corrections": 0})
