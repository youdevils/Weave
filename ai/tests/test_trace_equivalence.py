"""
Deterministic-outcome equivalence over the captured live flyer runs.

Each captured run's provider outputs are replayed through the current
workflow under one fixed provider policy (`EquivalenceReplay`), and the
deterministic result -- outcome, selected assertions, blocked targets and
their causes, open decisions -- is compared with a recorded baseline
(`fixtures/replay_baseline.json`, written from the code before an efficiency
change). An efficiency change may make fewer or smaller provider calls; it
may not change what the run decides.

The policy (ai.tests.test_reconcile_convergence.EquivalenceReplay) is keyed
by the work each call asks for, so a call a change makes unnecessary does not
shift later captured outputs onto the wrong request.

Budget: a change that removes calls also frees budget, and a freed call is
spent on work the baseline had to defer (a later round) -- a different run,
not a different decision. So each run is compared at the budget less the
calls removed since the baseline (`SAVED`): it must decide exactly what the
baseline decided, in exactly that many fewer calls. What the freed calls buy
at the full budget is pinned separately (`FreedBudgetTests`).

Determinism: the fixture model is built with fixed ids. A blocked root's
reported unmet requirements depend on requirement order, which follows rule
ids (the viability fixpoint in ai.services.reconcile.scope stops at a
cluster's first failing requirement, leaving the rest's satisfiers from an
earlier pass), so with random ids `causes` would differ from run to run.

The baseline is regenerated (at the full budget) with
ONYXJAR_UPDATE_REPLAY_BASELINE=1; ONYXJAR_REPLAY_REPORT=<file> appends each
run's sizes and call sequence (JSON lines) for reporting.
"""

import itertools
import json
import os
import tempfile
import uuid
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.db.models import UUIDField
from django.test import override_settings

from model.models.proposal import ProposalChange
from model.models.relationship_type_rule import RelationshipTypeRule

from ai.services.provider import canonical_payload
from ai.services.tracing import load
from ai.tests import test_reconcile_convergence as convergence
from ai.tests.test_reconcile_convergence import EquivalenceReplay, LateRoundFixture

TRACES = Path(__file__).parent / "fixtures" / "traces"
RUNS = ("10390789", "286357bd", "3f801647", "7f0fcac7", "f3e0d659", "1d854489")
BASELINE = Path(__file__).parent / "fixtures" / "replay_baseline.json"
COMPARED = ("outcome", "completeness", "selected", "created", "blocked", "causes", "open_decisions")
# Provider calls removed since the baseline: an Adjudication round that asked
# only indirect_classification questions (never asked now), and extraction
# corrections whose only items were unanchored claims no segment could
# anchor (dropped without the re-ask). Reset to zero when the baseline is
# regenerated.
SAVED = {"10390789": 2, "1d854489": 2, "286357bd": 1, "3f801647": 1, "7f0fcac7": 0, "f3e0d659": 1}
# Provider calls ADDED since the baseline: the one re-probe of a not_stated
# that its own pack's layout contests (ai.services.stages.gap_probe), and the
# correction a re-probe needs when its captured round never answered it.
# Reset to zero when the baseline is regenerated.
CONTESTED_CALLS = {"10390789": 2, "1d854489": 0, "286357bd": 1, "3f801647": 1, "7f0fcac7": 0, "f3e0d659": 0}
# The requirements (entity, relationship type) those re-probes contest, whose
# block report changes from coverage "complete" to "partial": the captured
# runs never answered the re-probe, so their evidence is not fully reviewed.
# Nothing else in what a run decides changes. Reset with the baseline.
TITLE = "PACIFIC INTERNATIONAL RUGBY CHAMPIONSHIP 2027"
CONTESTED = {
    "10390789": {(TITLE, "has_team_2"), ("Pool A", "has_match"), ("Pool B", "has_match"), ("Quarter-finals", "has_match"),
                 ("Sky Stadium", "played_at"), ("Forsyth Barr Stadium", "played_at"), ("FMG Stadium Waikato", "played_at"),
                 ("Orangetheory Stadium", "played_at")},
    "3f801647": {(TITLE, "has_team_2"), ("Orangetheory Stadium", "played_at")},
}


def contested(run, causes) -> dict:
    """The baseline's block causes with its contested requirements' coverage
    as the contest leaves it."""

    pairs = CONTESTED.get(run, set())
    result = {}
    for target, cause in causes.items():
        missing = []
        for entry in map(json.loads, cause["missing"]):
            if (entry.get("entity", target), entry["relationship_type_key"]) in pairs and entry.get("coverage") == "complete":
                entry["coverage"] = "partial"
            missing.append(json.dumps(entry, sort_keys=True))
        result[target] = {**cause, "missing": sorted(missing)}
    return result


def _selected(snapshot) -> list:
    ledger = {d["decision_id"]: d for d in snapshot.get("ledger", [])}
    rows = []
    for aid in snapshot.get("selected_assertions", []):
        source = (ledger.get(f"map:{aid}") or {}).get("source") or {}
        rows.append(f"{source.get('subject')} | {source.get('predicate')} | {source.get('object')}")
    return sorted(rows)


def _cause(blocked) -> dict:
    return {
        "reason": blocked.get("reason"),
        "missing": sorted(json.dumps(m, sort_keys=True) for m in blocked.get("missing_requirements", [])),
        "cascade": blocked.get("cascade"),
        "dependants": sorted(blocked.get("dependants", [])),
    }


class FlyerReplayCase(LateRoundFixture):
    """A captured live flyer run replayed under `EquivalenceReplay`, on the
    live model built with fixed ids, traced."""

    LIVE_RULE_IDS = convergence.LateRoundRegressionTests.LIVE_RULE_IDS

    def setUp(self):
        # Requirement order follows rule ids: fixed ids keep the fixture's
        # model identical from run to run (random ids reorder the report of
        # a blocked root's unmet requirements -- see the module docstring).
        counter = itertools.count(1)
        with mock.patch.object(UUIDField, "get_default", lambda field: uuid.UUID(int=next(counter))):
            super().setUp()
        self.trace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.trace_dir.cleanup)
        # Traced (selected assertions are read from the last analysis
        # snapshot): manage.py test forces DEBUG off, so the gate's env var too.
        env = mock.patch.dict(os.environ, {"DJANGO_DEBUG": "true"})
        env.start()
        self.addCleanup(env.stop)
        tracing = override_settings(AI_TRACE_DIR=self.trace_dir.name, RECONCILE_TRACE_ENABLED=True)
        tracing.enable()
        self.addCleanup(tracing.disable)

    def replay(self, run):
        rules = {r.relationship_type.key: str(r.id) for r in RelationshipTypeRule.objects.filter(relationship_type__model=self.model)}
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        for step in (TRACES / f"international_flyer_{run}").glob("*.json"):
            text = step.read_text(encoding="utf-8")
            for live, key in self.LIVE_RULE_IDS.items():
                text = text.replace(live, rules[key])
            (Path(directory.name) / step.name).write_text(text, encoding="utf-8")
        provider = EquivalenceReplay(directory.name)
        return provider, self.run_reconcile(provider)


    def observe(self, run) -> dict:
        provider, result = self.replay(run)
        steps = load(Path(self.trace_dir.name) / str(result.execution_id))
        analysis = [s["snapshot"] for s in steps if s["kind"] == "deterministic" and s["stage"] == "analysis"]
        verification = [p for stage, p in zip(provider.requested, provider.payloads) if stage == "verification"]
        sizes = {}
        for stage, payload in zip(provider.requested, provider.payloads):
            sizes.setdefault(stage, []).append(len(canonical_payload(payload)))
        return {
            "outcome": result.outcome.value,
            "completeness": result.completeness,
            "selected": _selected(analysis[-1]) if analysis else [],
            "created": sorted(c.after["name"] for c in ProposalChange.objects.filter(proposal_id=result.proposal_id)
                              if c.target_type == "Object" and c.operation == "create"),
            "blocked": sorted(b["target"] for b in result.blocked_targets),
            "causes": {b["target"]: _cause(b) for b in result.blocked_targets},
            "open_decisions": [d["question_id"] for d in verification[-1]["open_decisions"]] if verification else [],
            "requested": provider.requested,
            "payload_chars": sizes,
            "unaligned": provider.unaligned,
        }

    def report(self, run, observed, **extra):
        if os.getenv("ONYXJAR_REPLAY_REPORT"):
            with open(os.environ["ONYXJAR_REPLAY_REPORT"], "a", encoding="utf-8") as report:
                report.write(json.dumps({"run": run, **extra, **observed}) + "\n")

    @staticmethod
    def baseline(run) -> dict:
        return json.loads(BASELINE.read_text(encoding="utf-8"))[run]


class TraceEquivalenceTests(FlyerReplayCase):

    def check(self, run):
        if os.getenv("ONYXJAR_UPDATE_REPLAY_BASELINE") == "1":
            observed = self.observe(run)
            recorded = json.loads(BASELINE.read_text(encoding="utf-8")) if BASELINE.exists() else {}
            recorded[run] = observed
            BASELINE.write_text(json.dumps(recorded, indent=1, sort_keys=True), encoding="utf-8")
            return
        with override_settings(AI_WORKFLOW_MAX_PROVIDER_CALLS=settings.AI_WORKFLOW_MAX_PROVIDER_CALLS - SAVED[run] + CONTESTED_CALLS[run]):
            observed = self.observe(run)
        self.report(run, observed, budget="matched")
        expected = self.baseline(run)
        expected["causes"] = contested(run, expected["causes"])
        for field in COMPARED:
            self.assertEqual(observed[field], expected[field], f"{run}: {field} changed")
        self.assertEqual(len(observed["requested"]), len(expected["requested"]) - SAVED[run] + CONTESTED_CALLS[run], f"{run}: provider calls")


class FreedBudgetTests(FlyerReplayCase):
    """At the full budget, a freed call goes to work the baseline deferred --
    and only there."""

    def test_f3e0d659_the_freed_call_answers_the_decision_the_baseline_left_open(self):
        expected, observed = self.baseline("f3e0d659"), self.observe("f3e0d659")
        self.report("f3e0d659", observed, budget="full")

        self.assertEqual(expected["open_decisions"], ["predicate_mapping:has_team:tournament:team"])
        self.assertEqual(observed["open_decisions"], [])
        self.assertEqual(observed["requested"][-2:], ["adjudication", "verification"])
        self.assertEqual(len(observed["requested"]), len(expected["requested"]))
        # What that decision held back now compiles; what the evidence never
        # supported stays blocked.
        self.assertEqual((expected["outcome"], observed["outcome"]), ("unresolved", "ready_for_review"))
        self.assertTrue(set(observed["blocked"]) < set(expected["blocked"]))
        self.assertEqual(set(observed["blocked"]), {"Final", "McLean Park", "Orangetheory Stadium", "Quarter-final", "Semi-final"})

    def test_10390789_the_freed_calls_go_to_the_contested_re_probes(self):
        expected, observed = self.baseline("10390789"), self.observe("10390789")
        self.report("10390789", observed, budget="full")

        # The calls freed since the baseline are now spent re-probing the
        # absences its layout contests (CONTESTED) -- before the round that
        # used to review deferred evidence; the run still ends adjudicating.
        self.assertEqual(observed["requested"][-2:], ["adjudication", "verification"])
        self.assertEqual(observed["requested"].count("gap_probe_correction"), CONTESTED_CALLS["10390789"])
        self.assertEqual(len(observed["requested"]), len(expected["requested"]) - SAVED["10390789"] + CONTESTED_CALLS["10390789"])
        # No decision changes; only the contested requirements' coverage.
        for field in ("outcome", "completeness", "selected", "created", "blocked", "open_decisions"):
            self.assertEqual(observed[field], expected[field], field)
        self.assertEqual(observed["causes"], contested("10390789", expected["causes"]))


for _run in RUNS:
    setattr(TraceEquivalenceTests, f"test_run_{_run}", lambda self, run=_run: self.check(run))
