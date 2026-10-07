"""
Opt-in run tracing for investigating live runs (dev only).

Persistence policy is unchanged: AIExecution / AIExecutionStep keep digests
and codes only, never payloads. When the AI_TRACE_DIR setting is set (it is
unset by default), the engine additionally writes each step of a run to
`<AI_TRACE_DIR>/<execution id>/<seq>-<stage>.json` on local disk:

    provider steps      the payload sent, the parsed output, the schema
    deterministic steps a snapshot of the Reconcile state: ingress log
                        (every claim's ingress fate), Decision Ledger,
                        scope outcomes, coverage, blocked targets

`ReplayProvider` re-serves a trace's outputs in order, so a live run becomes
a deterministic regression; `fate_table` summarises what happened to every
evidence claim.
"""

from __future__ import annotations

import json
from pathlib import Path

from django.conf import settings

from ai.services.provider import AIProvider, ProviderResult


def trace_dir(execution_id) -> Path | None:
    root = getattr(settings, "AI_TRACE_DIR", None)
    if not root:
        return None
    path = Path(root) / str(execution_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_step(execution_id, sequence, stage, record: dict) -> None:
    path = trace_dir(execution_id)
    if path is None:
        return
    (path / f"{sequence:03d}-{stage}.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")


def reconcile_snapshot(state) -> dict:
    rs = getattr(state, "reconcile", None)
    if rs is None:
        return {}
    analysis = rs.analysis
    snapshot = {
        "graph_ids": sorted(rs.graph.ids()),
        "ingress": list(rs.ingress_log),
        "pending": {k: [i.message for i in v[1]] for k, v in rs.pending_items.items()},
        "probe_outcomes": dict(rs.probe_outcomes),
        "dismissals": dict(rs.dismissals),
        "pins": {k: {"option_id": p.option_id, "basis": p.basis, **({"reason": p.reason} if getattr(p, "reason", "") else {})}
                 for k, p in rs.pins.items()},
        "asked": sorted(rs.asked),
        "probed": sorted(rs.probed),
        "work_queue": rs.work_queue.payload() if getattr(rs, "work_queue", None) is not None else None,
        "unframed": dict(getattr(rs, "unframed", {}) or {}),
        "frame_repairs": dict(getattr(rs, "frame_repairs", {}) or {}),
    }
    if analysis is not None:
        snapshot.update({
            "ledger": analysis.ledger.payload(),
            "scope_outcomes": {analysis.cluster_name(c): o for c, o in analysis.scope.outcomes.items()},
            "selected_assertions": sorted(analysis.scope.selected_assertions),
            "coverage": {k: v.status for k, v in analysis.coverage.items()},
            "questions": [{"question_id": x.question_id, "kind": x.kind, "subject_ids": x.subject_ids} for x in analysis.questions],
            "probe_requests": [r.requirement_id for r in analysis.probe_requests],
            "target_status": list(getattr(analysis, "target_status", []) or []),
        })
    snapshot["blocked_targets"] = list(getattr(state, "blocked_targets", []) or [])
    return snapshot


def load(path) -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(path).glob("*.json"))]


class ReplayProvider(AIProvider):
    """Re-serves a captured run's provider outputs.

    Strict (default): in captured order, each requested by the stage it was
    captured from. By stage (`by_stage=True`, or whenever `inject` is given):
    each stage's captured outputs in their own order, so a run whose routing
    has changed can still be replayed -- `inject` = {stage: [output dict or
    callable(payload) -> output dict]} is served AFTER that stage's captured
    outputs (a counterfactual: e.g. the answers the extra Adjudication rounds
    of a re-routed run would give).
    `requested` / `payloads` record the stages asked for and what each was
    sent, in order."""

    def __init__(self, path, *, by_stage=False, inject=None):
        steps = load(path)
        self.steps = [s for s in steps if s.get("kind") == "provider"]
        self.explanations = [s for s in steps if s.get("kind") == "explain"]
        self.index = 0
        self.by_stage = by_stage or inject is not None
        self.queues: dict[str, list] = {}
        for step in self.steps:
            self.queues.setdefault(step["stage"], []).append(step["output"])
        for stage, outputs in (inject or {}).items():
            self.queues.setdefault(stage, []).extend(outputs)
        self.requested: list[str] = []
        self.payloads: list[dict] = []

    def generate_structured(self, *, system_prompt, user_payload, response_schema, config):
        stage = user_payload.get("stage")
        self.requested.append(stage)
        self.payloads.append(user_payload)
        if self.by_stage:
            queue = self.queues.get(stage) or []
            if not queue:
                raise AssertionError(f"Replay has no output left for stage {stage!r}.")
            output = queue.pop(0)
            output = output(user_payload) if callable(output) else output
            return ProviderResult(parsed=response_schema.model_validate(output), raw_text="", usage={}, provider="replay")
        if self.index >= len(self.steps):
            raise AssertionError("Replay ran out of captured outputs.")
        step = self.steps[self.index]
        self.index += 1
        if step["stage"] != stage:
            raise AssertionError(f"Replay diverged: captured {step['stage']}, requested {stage}.")
        return ProviderResult(parsed=response_schema.model_validate(step["output"]), raw_text="", usage={}, provider="replay")

    def explain(self, *, context, issues, config):
        text = self.explanations[0]["output"] if self.explanations else ""
        return ProviderResult(parsed=None, raw_text=text, usage={}, provider="replay")


def fate_table(snapshot: dict) -> list[dict]:
    """Every evidence claim's fate in one deterministic snapshot: ingress,
    grounding, mapping/identity, scope."""

    ledger = {d["decision_id"]: d for d in snapshot.get("ledger", [])}
    rows = []
    for entry in snapshot.get("ingress", []):
        identifier = entry.get("id")
        rows.append({
            "id": identifier,
            "origin": entry.get("origin"),
            "ingress": entry.get("outcome"),
            "reason": entry.get("reason", ""),
            "ground": ledger.get(f"ground:{identifier}", {}).get("outcome"),
            "mapping": (ledger.get(f"map:{identifier}") or ledger.get(f"type:{identifier}") or ledger.get(f"fact:{identifier}") or {}).get("outcome"),
            "scope": (ledger.get(f"esc:{identifier}") or {}).get("outcome"),
        })
    return rows
