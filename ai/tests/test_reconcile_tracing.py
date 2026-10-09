"""
The Reconcile trace capability (ai/README.md; ai.services.tracing): opt-in,
dev-only capture of a live run's payloads/outputs and deterministic state,
gated so it can never activate in production regardless of what else is
set, and never changes what a run produces.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, override_settings

from ai.services.tracing import compact_snapshot, expand_snapshots, load, requirement_table, run_summary, trace_active
from ai.tests.rugby import INTENT
from ai.tests.support import ScriptedProvider, answers, approve, assertion, entity, extraction, frame, graph, probe, target, verdict
from ai.tests.test_reconcile_workflow import ReconcileWorkflowTestCase
from ai.tests.test_structural_anchors import FIXTURE_ROW, OTHER_MATCH_ROW, TEXT, VENUE_ROW


class TraceActiveGateTests(ReconcileWorkflowTestCase):
    """The gate itself: DJANGO_DEBUG=false always wins, regardless of the
    other two settings -- checked against the literal env var, since
    `manage.py test` forces `settings.DEBUG = False` for the whole suite
    (Django's own DiscoverRunner) in a way `override_settings(DEBUG=...)`
    cannot restore per test."""

    def test_disabled_by_default(self):
        self.assertIsNone(getattr(self, "_no_ai_trace_dir_set", None))  # sanity: no override active here
        # "Default" = no AI_TRACE_DIR configured; the dev container's
        # .env.dev configures one, so state the default explicitly.
        with override_settings(AI_TRACE_DIR=None):
            self.assertFalse(trace_active())

    def test_inactive_when_debug_env_is_false_even_with_everything_else_on(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(AI_TRACE_DIR=tmp, RECONCILE_TRACE_ENABLED=True), \
             mock.patch.dict(os.environ, {"DJANGO_DEBUG": "false"}):
            self.assertFalse(trace_active())
            result = self.run_reconcile(ScriptedProvider([self.flyer_extraction(), approve()]))
            self.assertFalse(list(Path(tmp).glob("*")))
            self.assertEqual(result.outcome.value, "ready_for_review")

    def test_active_when_debug_env_is_true_and_the_flag_is_on(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(AI_TRACE_DIR=tmp, RECONCILE_TRACE_ENABLED=True), \
             mock.patch.dict(os.environ, {"DJANGO_DEBUG": "true"}):
            self.assertTrue(trace_active())

    def test_the_explicit_flag_is_an_independent_kill_switch(self):
        with tempfile.TemporaryDirectory() as tmp, override_settings(AI_TRACE_DIR=tmp, RECONCILE_TRACE_ENABLED=False), \
             mock.patch.dict(os.environ, {"DJANGO_DEBUG": "true"}):
            self.assertFalse(trace_active())

    def test_no_ai_trace_dir_means_inactive_even_with_debug_and_flag_on(self):
        with override_settings(AI_TRACE_DIR=None, RECONCILE_TRACE_ENABLED=True), mock.patch.dict(os.environ, {"DJANGO_DEBUG": "true"}):
            self.assertFalse(trace_active())


class _TracedRunTestCase(ReconcileWorkflowTestCase):
    """Turns tracing genuinely on for the duration of the test: DJANGO_DEBUG
    is patched (manage.py test forces it false for the suite) alongside the
    settings the gate also checks."""

    def setUp(self):
        super().setUp()
        self.trace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.trace_dir.cleanup)
        env_patch = mock.patch.dict(os.environ, {"DJANGO_DEBUG": "true"})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        settings_patch = override_settings(AI_TRACE_DIR=self.trace_dir.name, RECONCILE_TRACE_ENABLED=True)
        settings_patch.enable()
        self.addCleanup(settings_patch.disable)

    def files_for(self, result):
        return load(Path(self.trace_dir.name) / str(result.execution_id))


class MultiCallTraceTests(_TracedRunTestCase):

    def test_run_id_and_sequence_correlate_every_call_including_repeats(self):
        provider = ScriptedProvider([
            self.flyer_extraction(),
            answers(("identity:E6", "wembley", "Eden Park")),  # invalid option -> re-asked
            answers(("identity:E6", "eden_park", "Eden Park")),
            approve(),
        ])
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park")
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park_old")

        result = self.run_reconcile(provider)

        steps = self.files_for(result)
        self.assertTrue(trace_active())
        self.assertTrue(steps)
        sequences = [s["sequence"] for s in steps]
        self.assertEqual(sequences, sorted(sequences))
        self.assertEqual(sequences, list(range(1, len(steps) + 1)))  # strictly increasing, gapless
        for s in steps:
            self.assertEqual(s["run_id"], str(result.execution_id))
        # Two adjudication calls (the repeat): both present, in order.
        adjudications = [s for s in steps if s.get("stage") == "adjudication"]
        self.assertEqual(len(adjudications), 2)
        self.assertEqual([s["sequence"] for s in adjudications], sorted(s["sequence"] for s in adjudications))

    def test_provider_step_carries_genuine_call_timing_and_identity(self):
        result = self.run_reconcile(ScriptedProvider([self.flyer_extraction(), approve()]))

        extraction_step = next(s for s in self.files_for(result) if s.get("stage") == "extraction" and s["kind"] == "provider")
        self.assertEqual(extraction_step["provider"], "test")
        self.assertIn("provider_model", extraction_step)
        self.assertIn("total_tokens", extraction_step["usage"])
        self.assertLessEqual(extraction_step["started_at"], extraction_step["ended_at"])

    def test_untraced_and_traced_runs_produce_the_same_result(self):
        traced = self.run_reconcile(ScriptedProvider([self.flyer_extraction(), approve()]))
        with override_settings(AI_TRACE_DIR=None):
            untraced = self.run_reconcile(ScriptedProvider([self.flyer_extraction(), approve()]))

        self.assertEqual((traced.outcome, traced.completeness), (untraced.outcome, untraced.completeness))
        self.assertEqual(self.created_names(traced), self.created_names(untraced))


class AnchorsTraceTests(_TracedRunTestCase):
    """`relationship_anchors()`'s own standalone, correlatable trace event."""

    def setUp(self):
        super().setUp()
        self.model = self.make_model(name="Fixtures")
        self.venue = self.make_object_type(self.model, key="venue")
        self.match = self.make_object_type(self.model, key="match")
        self.played_at = self.make_relationship_type(self.model, key="played_at")
        self.make_rule(self.played_at, self.match, self.venue, object_minimum=1, subject_minimum=1, subject_maximum=1)

    def wrong_citation(self):
        venue = entity("E1", "FMG Stadium Waikato", "venue", hint="venue", excerpt="FMG Stadium Waikato")
        venue.provenance[0].segment_id = VENUE_ROW
        match = entity("E2", "South Africa v Tonga", "match", hint="match", excerpt="South Africa v Tonga")
        match.provenance[0].segment_id = FIXTURE_ROW
        wrong = assertion("A1", "E2", "is played at", "E1", hint="played_at", excerpt="FMG Stadium Waikato")
        wrong.provenance[0].segment_id = VENUE_ROW  # wrong: the venue's own row, not the fixture row
        return extraction(frame([target("T1", "venues", "venues", hint="venue")]), venue, match, wrong)

    def fixed_citation(self):
        fixed = assertion("A1", "E2", "is played at", "E1", hint="played_at", excerpt="South Africa v Tonga | FMG Stadium Waikato")
        fixed.provenance[0].segment_id = FIXTURE_ROW
        # The other fixture row (Eden Park's) is irrelevant to this scenario;
        # dismiss it so it doesn't become an uncovered venue-relevant segment
        # and route an unrelated Gap Probe round.
        return extraction(frame(), fixed, dismissed=[(OTHER_MATCH_ROW, "Not relevant to this test scenario.")])

    @staticmethod
    def _settle(payload):
        """Whatever else the run still needs after the citation is fixed
        (this scenario's own concern is the anchor event, not the exact
        route): close out any further gap probe honestly, approve otherwise."""

        if payload.get("stage", "").startswith("gap_probe"):
            return probe(verdicts=[verdict(r["requirement_id"], "not_stated") for r in payload.get("requirements", [])])
        return approve()

    def test_an_anchor_event_correlates_with_its_own_calls_sequence(self):
        from ai.services.orchestrator import run_ai_operation

        provider = ScriptedProvider([self.wrong_citation(), self.fixed_citation(), self._settle, self._settle, self._settle])
        result = run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=INTENT,
                                  assets=[{"name": "flyer.txt", "content": TEXT}], provider=provider)

        steps = self.files_for(result)
        correction_step = next(s for s in steps if s.get("stage") == "extraction_correction" and s["kind"] == "provider")
        anchors_path = Path(self.trace_dir.name) / str(result.execution_id) / "anchors.jsonl"
        self.assertTrue(anchors_path.exists())
        lines = [json.loads(line) for line in anchors_path.read_text(encoding="utf-8").splitlines()]
        line = next(l for l in lines if l["item_id"] == "A1")

        self.assertEqual(line["run_id"], str(result.execution_id))
        self.assertEqual(line["sequence"], correction_step["sequence"])
        self.assertEqual(line["stage"], "extraction_correction")
        self.assertEqual(line["subject"], "South Africa v Tonga")
        self.assertEqual(line["object"], "FMG Stadium Waikato")
        self.assertEqual(line["anchors"]["direct"], [FIXTURE_ROW])


class SummaryAndRequirementTableTests(_TracedRunTestCase):

    def test_run_summary_and_requirement_table_match_the_snapshot_by_hand(self):
        result = self.run_reconcile(ScriptedProvider([self.flyer_extraction(), approve()]))

        snapshot = next(s["snapshot"] for s in reversed(self.files_for(result)) if s["kind"] == "deterministic")

        summary = run_summary(snapshot)
        self.assertEqual(summary["graph"]["total"], len(snapshot["graph_ids"]))
        self.assertEqual(sum(summary["ingress_outcomes"].values()), len(snapshot["ingress"]))
        self.assertEqual(summary["blocked_targets"], len(snapshot["blocked_targets"]))
        self.assertEqual(summary["selected_assertions"], len(snapshot["selected_assertions"]))

        rows = requirement_table(snapshot)
        by_hand = [
            {"relationship_type_key": r["relationship_type_key"], "candidates": r["candidates"], "satisfied_by": r["satisfied_by"]}
            for d in snapshot["ledger"] if d["decision_id"].startswith("esc:") and d.get("step") == "scope"
            for r in (d.get("detail") or {}).get("requirements", [])
        ]
        self.assertEqual(len(rows), len(by_hand))
        self.assertTrue(all(row["viable"] == (len(row["satisfied_by"]) >= row["minimum"]) for row in rows))


class TraceSizeAndCompactionTests(_TracedRunTestCase):
    """What each call cost to send is recorded with it; the Decision Ledger
    is written once and then as deltas, and `load()` restores every
    snapshot exactly."""

    def two_analyses(self):
        """Analysis -> Adjudication -> analysis -> compile: two analysis
        snapshots, so the second is written as a delta."""

        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park")
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park_old")
        return ScriptedProvider([self.flyer_extraction(), answers(("identity:E6", "eden_park", "Eden Park")), approve()])

    def test_a_provider_step_records_what_the_call_sent(self):
        from ai.services.provider import canonical_payload
        from ai.services.reconcile.responses import ExtractionResult

        provider = ScriptedProvider([self.flyer_extraction(), approve()])
        result = self.run_reconcile(provider)

        step = next(s for s in self.files_for(result) if s["kind"] == "provider" and s["stage"] == "extraction")
        sent = canonical_payload(step["payload"])
        self.assertEqual(step["payload_chars"], len(sent))
        self.assertEqual(set(step["payload_sections"]), set(step["payload"]))
        self.assertEqual(step["payload_sections"]["segments"], len(canonical_payload(step["payload"]["segments"])))
        # Sections plus their keys and separators make up the whole payload.
        self.assertLess(sum(step["payload_sections"].values()), step["payload_chars"])
        self.assertGreater(step["system_prompt_chars"], 0)
        self.assertEqual(step["schema_chars"], len(canonical_payload(ExtractionResult.model_json_schema())))

    def test_the_ledger_is_written_once_then_as_deltas_and_compile_writes_it_whole(self):
        result = self.run_reconcile(self.two_analyses())

        on_disk = [json.loads(p.read_text(encoding="utf-8"))
                   for p in sorted((Path(self.trace_dir.name) / str(result.execution_id)).glob("*.json"))]
        analyses = [s for s in on_disk if s["kind"] == "deterministic" and s["stage"] == "analysis"]
        self.assertGreaterEqual(len(analyses), 2)
        self.assertIn("ledger", analyses[0]["snapshot"])
        for later in analyses[1:]:
            self.assertNotIn("ledger", later["snapshot"])
            self.assertIn("ledger_delta", later["snapshot"])
        compile_step = next(s for s in on_disk if s["kind"] == "deterministic" and s["stage"] == "compile")
        self.assertIn("ledger", compile_step["snapshot"])

    def test_load_restores_exactly_the_snapshots_the_run_produced(self):
        from ai.services.workflow import engine

        produced = []
        original = engine.reconcile_snapshot

        def capture(state):
            snapshot = original(state)
            produced.append(json.loads(json.dumps(snapshot, default=str)))
            return snapshot

        with mock.patch.object(engine, "reconcile_snapshot", capture):
            result = self.run_reconcile(self.two_analyses())

        loaded = [s["snapshot"] for s in self.files_for(result) if s["kind"] == "deterministic"]
        self.assertEqual(len(loaded), len(produced))
        for restored, expected in zip(loaded, produced):
            self.assertEqual(restored, expected)


class SnapshotCompactionUnitTests(SimpleTestCase):

    @staticmethod
    def decision(key, outcome="x"):
        return {"decision_id": key, "outcome": outcome}

    def round_trip(self, *ledgers):
        written, previous = [], None
        for sequence, ledger in enumerate(ledgers, 1):
            snapshot, previous = compact_snapshot({"ledger": ledger, "other": sequence}, previous, sequence=sequence)
            written.append({"sequence": sequence, "snapshot": json.loads(json.dumps(snapshot))})
        return written, [s["snapshot"] for s in expand_snapshots(written)]

    def test_added_changed_removed_and_reordered_decisions_round_trip(self):
        first = [self.decision("a"), self.decision("b"), self.decision("c")]
        second = [self.decision("d"), self.decision("a", "y"), self.decision("c")]  # d new and first, a changed, b removed
        third = [self.decision("d"), self.decision("a", "y"), self.decision("c")]  # unchanged

        written, restored = self.round_trip(first, second, third)

        delta = written[1]["snapshot"]["ledger_delta"]
        self.assertEqual(([d["decision_id"] for d in delta["added"]], [d["decision_id"] for d in delta["changed"]], delta["removed"]),
                         (["d"], ["a"], ["b"]))
        self.assertEqual(delta["order"], ["d", "a", "c"])
        self.assertEqual(written[2]["snapshot"]["ledger_delta"], {"base_sequence": 2, "added": [], "changed": [], "removed": []})
        self.assertEqual(restored, [{"ledger": first, "other": 1}, {"ledger": second, "other": 2}, {"ledger": third, "other": 3}])

    def test_a_full_step_resets_the_base(self):
        snapshot, previous = compact_snapshot({"ledger": [self.decision("a")]}, None, sequence=1)
        snapshot, previous = compact_snapshot({"ledger": [self.decision("b")]}, previous, sequence=2, full=True)

        self.assertEqual(snapshot, {"ledger": [self.decision("b")]})
        self.assertEqual(previous["sequence"], 2)

    def test_a_delta_without_its_base_is_an_error_not_a_guess(self):
        with self.assertRaises(ValueError):
            expand_snapshots([{"sequence": 3, "snapshot": {"ledger_delta": {"base_sequence": 2, "added": [], "changed": [], "removed": []}}}])
