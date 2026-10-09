"""
The Phase 5 default-flip gate, LIVE tier (.Documentation/reconcile-architecture-plan.md,
Phase 5): every canonical document run ONYXJAR_GATE_RUNS times (default 5)
in each evidence mode against the real provider; each reference-spec
assertion's pass rate recorded per mode, with calls / tokens / payload size.

Opt-in (it spends provider tokens):

    ONYXJAR_LIVE_AI_TESTS=1 ONYXJAR_GATE=1 [ONYXJAR_GATE_RUNS=5] \\
    [ONYXJAR_GATE_REPORT=/app/.ai-traces/gate_report.json] \\
        python manage.py test ai.tests.test_live_gate

Live output is stochastic, so this tier is evidence, not correctness -- the
hard gate is the scripted / replayed tiers (ai.tests.test_readings,
test_readings_canonical). Its rules (plan, Phase 5):

    FAIL    any forbidden change in any readings-mode run (a safety property)
    FLAG    an assertion readings passes in < 60% of runs while claims passes
            it in >= 80% -- investigate and record a decision
    FLAG    on the flyer, readings reaches every required positive in fewer
            than 3 of 5 runs (the claims-mode baseline is 0 of 7)
"""

import json
import os
import unittest
from collections import defaultdict
from pathlib import Path

from django.test import override_settings

from ai.models import AIExecution
from ai.services.orchestrator import run_ai_operation
from ai.tests.reference import evaluate, load_spec, outcome_from_proposal
from ai.tests.rugby import FLYER_ASSETS, INTENT as RUGBY_INTENT, RugbyFixture
from ai.tests.test_governance_contract import INTENT as FLYER_INTENT, GovernanceContractTestCase
from ai.tests.test_reconcile_resilience import ASSETS as DEPTH_ASSETS, INTENT as DEPTH_INTENT, DepthFixture
from ai.tests.test_reference_specs import REPORT_ASSETS

LIVE = os.environ.get("ONYXJAR_LIVE_AI_TESTS") == "1" and os.environ.get("ONYXJAR_GATE") == "1"
RUNS = int(os.environ.get("ONYXJAR_GATE_RUNS", "5"))
REPORT = Path(os.environ.get("ONYXJAR_GATE_REPORT", "reconcile_gate_report.json"))
POSITIVE_KEYS = ("required_objects", "required_relationships")


def gate(document, spec_name, results_by_mode) -> dict:
    """The plan's live-tier rules over {mode: [[Check], ...]}."""

    spec = load_spec(spec_name)
    positives = {item["id"] for key in POSITIVE_KEYS for item in spec[key]}
    forbidden = {item["id"] for key in ("forbidden_objects", "forbidden_relationships") for item in spec[key]}
    rates = {}
    for mode, runs in results_by_mode.items():
        counts = defaultdict(int)
        for checks in runs:
            for check in checks:
                counts[check.id] += check.passed
        rates[mode] = {k: v / max(len(runs), 1) for k, v in counts.items()}
    failures, flags = [], []
    for checks in results_by_mode.get("readings", []):
        failures += [f"forbidden change: {c.id} ({c.detail})" for c in checks if c.id in forbidden and not c.passed]
    for assertion_id, claims_rate in rates.get("claims", {}).items():
        if claims_rate >= 0.8 and rates.get("readings", {}).get(assertion_id, 0) < 0.6:
            flags.append(f"{assertion_id}: claims {claims_rate:.0%}, readings {rates['readings'].get(assertion_id, 0):.0%}")
    if spec_name == "international_flyer":
        complete = sum(all(c.passed for c in checks if c.id in positives) for checks in results_by_mode.get("readings", []))
        if complete < min(3, RUNS):
            flags.append(f"readings reached every required positive in {complete} of {RUNS} runs")
    return {"document": document, "rates": rates, "failures": sorted(set(failures)), "flags": flags}


class _GateMixin:
    SPEC = ""
    INTENT = ""

    def assets_for_gate(self):
        raise NotImplementedError

    def run_gate(self):
        results, measures = defaultdict(list), defaultdict(list)
        modes = [m for m in os.environ.get("ONYXJAR_GATE_MODES", "claims,readings").split(",") if m]
        for mode in modes:
            for _ in range(RUNS):
                # Every run keeps its Proposal: lift the per-model live-proposal cap
                # for the gate, and trace into the gate's own directory (a fixture
                # may point AI_TRACE_DIR at a temporary one).
                with override_settings(AI_RECONCILE_EVIDENCE_MODE=mode, PROPOSAL_MAX_LIVE_PER_MODEL=10_000,
                                       AI_TRACE_DIR=os.environ.get("AI_TRACE_DIR") or None):
                    result = run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=self.INTENT,
                                              assets=self.assets_for_gate(), provider=None)
                checks = evaluate(outcome_from_proposal(result.proposal_id, result.blocked_targets), load_spec(self.SPEC))
                results[mode].append(checks)
                execution = AIExecution.objects.get(pk=result.execution_id)
                measures[mode].append({"execution_id": str(result.execution_id), "outcome": result.outcome.value, "calls": result.provider_calls,
                                       "tokens": (execution.usage or {}).get("total_tokens"), "stages": result.stage_summary,
                                       "passed": sum(c.passed for c in checks), "of": len(checks),
                                       "failed": {c.id: c.detail for c in checks if not c.passed}})
        verdict = gate(self.SPEC, self.SPEC, results)
        verdict["measures"] = measures
        recorded = json.loads(REPORT.read_text(encoding="utf-8")) if REPORT.exists() else {}
        recorded[self.SPEC] = verdict
        REPORT.write_text(json.dumps(recorded, indent=1, default=str), encoding="utf-8")
        print(f"\nGATE {self.SPEC}: failures={verdict['failures']} flags={verdict['flags']} -> {REPORT}")
        self.assertEqual(verdict["failures"], [])


@unittest.skipUnless(LIVE, "Set ONYXJAR_LIVE_AI_TESTS=1 and ONYXJAR_GATE=1 to run the live gate.")
class FlyerGate(_GateMixin, GovernanceContractTestCase):
    SPEC, INTENT = "international_flyer", FLYER_INTENT

    def assets_for_gate(self):
        return self.assets

    def test_gate(self):
        self.run_gate()


@unittest.skipUnless(LIVE, "Set ONYXJAR_LIVE_AI_TESTS=1 and ONYXJAR_GATE=1 to run the live gate.")
class ReportGate(_GateMixin, GovernanceContractTestCase):
    SPEC, INTENT = "international_report", FLYER_INTENT

    def assets_for_gate(self):
        return REPORT_ASSETS

    def test_gate(self):
        self.run_gate()


@unittest.skipUnless(LIVE, "Set ONYXJAR_LIVE_AI_TESTS=1 and ONYXJAR_GATE=1 to run the live gate.")
class RugbyFlyerGate(_GateMixin, RugbyFixture):
    SPEC, INTENT = "rugby_flyer", RUGBY_INTENT

    def assets_for_gate(self):
        return FLYER_ASSETS

    def test_gate(self):
        self.run_gate()


@unittest.skipUnless(LIVE, "Set ONYXJAR_LIVE_AI_TESTS=1 and ONYXJAR_GATE=1 to run the live gate.")
class DepthChainGate(_GateMixin, DepthFixture):
    SPEC, INTENT = "depth_chain", DEPTH_INTENT

    def assets_for_gate(self):
        return DEPTH_ASSETS

    def test_gate(self):
        self.run_gate()


class GateRuleTests(unittest.TestCase):
    """The gate's own rules, on synthetic pass/fail patterns (no provider)."""

    def checks(self, passed):
        from ai.tests.reference import Check
        spec = load_spec("international_flyer")
        ids = [item["id"] for key in spec if key not in ("document", "description") for item in spec[key]]
        return [Check(i, passed(i)) for i in ids]

    def test_a_forbidden_change_in_readings_mode_fails_the_gate(self):
        verdict = gate("flyer", "international_flyer", {
            "claims": [self.checks(lambda i: True)],
            "readings": [self.checks(lambda i: i != "forbidden:placeholder_teams")],
        })
        self.assertEqual(len(verdict["failures"]), 1)

    def test_a_readings_regression_on_a_claims_strength_is_flagged_not_failed(self):
        verdict = gate("flyer", "international_flyer", {
            "claims": [self.checks(lambda i: True)] * 5,
            "readings": [self.checks(lambda i: i != "venue:eden_park")] * 5,
        })
        self.assertEqual(verdict["failures"], [])
        self.assertTrue(any("venue:eden_park" in f for f in verdict["flags"]))
