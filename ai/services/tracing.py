"""
Opt-in run tracing for investigating live runs (dev only).

Persistence policy is unchanged: AIExecution / AIExecutionStep keep digests
and codes only, never payloads. When tracing is active (`trace_active()`),
the engine additionally writes each step of a run to
`<AI_TRACE_DIR>/<execution id>/<seq>-<stage>.json` on local disk:

    provider steps      the payload sent, the parsed output, the schema,
                        the provider/model and usage, and the call's own
                        started_at/ended_at
    deterministic steps a snapshot of the Reconcile state: ingress log
                        (every claim's ingress fate), Decision Ledger,
                        scope outcomes, coverage, blocked targets

plus one `anchors.jsonl` per run (`trace_anchors`) recording each
`relationship_anchors()` computation as its own correlatable event.

Tracing is gated by three settings (`AI_TRACE_DIR`, `RECONCILE_TRACE_ENABLED`,
and Django's own `DEBUG`) combined by `trace_active()` -- DEBUG=False always
disables it, whatever the other two say. `trace_active()` re-reads live
settings on every call (not a frozen constant) so `override_settings` in
tests works normally.

`ReplayProvider` re-serves a trace's outputs in order, so a live run becomes
a deterministic regression; `fate_table` summarises what happened to every
evidence claim; `run_summary`/`requirement_table` reshape an existing
snapshot into compact, directly-readable views -- no new interpretation.
"""

from __future__ import annotations

import json
from collections import Counter
import os
from pathlib import Path

from django.conf import settings

from ai.services.provider import AIProvider, ProviderResult


def trace_active() -> bool:
    """The production-safety gate: reads DJANGO_DEBUG itself (the literal
    source `settings.DEBUG` is computed from -- `onyxjar/settings.py`'s
    `DEBUG = os.getenv("DJANGO_DEBUG", "false").lower() == "true"`), not the
    `settings.DEBUG` attribute. `manage.py test`'s runner unconditionally
    sets `settings.DEBUG = False` for the whole suite (Django's own
    `DiscoverRunner`, `debug_mode=False` by default) with no way to opt out
    per test-case via `override_settings` in the usual way that would help
    here; reading the env var directly keeps the same real invariant (a
    deployed, DJANGO_DEBUG=false production process can never trace) without
    that unrelated test-runner behaviour silently disabling every existing
    trace-dependent test."""

    debug = os.getenv("DJANGO_DEBUG", "false").lower() == "true"
    return debug and bool(getattr(settings, "RECONCILE_TRACE_ENABLED", True)) and bool(getattr(settings, "AI_TRACE_DIR", None))


def trace_dir(execution_id) -> Path | None:
    if not trace_active():
        return None
    path = Path(settings.AI_TRACE_DIR) / str(execution_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_step(execution_id, sequence, stage, record: dict) -> None:
    path = trace_dir(execution_id)
    if path is None:
        return
    (path / f"{sequence:03d}-{stage}.json").write_text(json.dumps(record, indent=1, default=str), encoding="utf-8")


def trace_anchors(execution_id, sequence, stage, item_id, *, subject, object, anchors: dict) -> None:
    """One `relationship_anchors()` computation, appended to
    `<dir>/<execution_id>/anchors.jsonl` -- correlated by `sequence` with
    that call's own `<seq>-<stage>.json`, so it's findable without opening
    the full stage payload."""

    path = trace_dir(execution_id)
    if path is None:
        return
    record = {"run_id": str(execution_id), "sequence": sequence, "stage": stage, "item_id": item_id,
             "subject": subject, "object": object, "anchors": anchors}
    with (path / "anchors.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


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


def run_summary(snapshot: dict) -> dict:
    """Compact counts, tallied from an existing deterministic snapshot --
    no new interpretation of the run, just a readable total of what's
    already there."""

    ids = snapshot.get("graph_ids", [])
    entities = sum(1 for i in ids if i.startswith(("E", "e")))
    assertions = sum(1 for i in ids if i.startswith(("A", "a")))
    facts = sum(1 for i in ids if i.startswith(("F", "f")))
    return {
        "graph": {"entities": entities, "assertions": assertions, "facts": facts, "total": len(ids)},
        "ingress_outcomes": dict(Counter(e.get("outcome") for e in snapshot.get("ingress", []))),
        "scope_outcomes": dict(Counter(snapshot.get("scope_outcomes", {}).values())),
        "coverage": dict(Counter(snapshot.get("coverage", {}).values())),
        "blocked_targets": len(snapshot.get("blocked_targets", []) or []),
        "selected_assertions": len(snapshot.get("selected_assertions", []) or []),
        "questions": len(snapshot.get("questions", []) or []),
        "probe_requests": len(snapshot.get("probe_requests", []) or []),
        "route": (snapshot.get("work_queue") or {}).get("route"),
    }


def requirement_table(snapshot: dict) -> list[dict]:
    """Every scope requirement in the run's last analysis, flattened from
    the Decision Ledger's `esc:` decisions (`scope.py`'s own detail) into
    one flat, directly-readable list: entity, relationship, minimum,
    candidates, satisfied_by, and whether it was met."""

    rows = []
    for decision in snapshot.get("ledger", []):
        if decision.get("step") != "scope" or not decision.get("decision_id", "").startswith("esc:"):
            continue
        detail = decision.get("detail") or {}
        for requirement in detail.get("requirements", []):
            satisfied_by = requirement.get("satisfied_by") or []
            rows.append({
                "entity": detail.get("name"),
                "relationship_type_key": requirement.get("relationship_type_key"),
                "counterpart_type_key": requirement.get("counterpart_type_key"),
                "minimum": requirement.get("minimum"),
                "candidates": requirement.get("candidates"),
                "satisfied_by": satisfied_by,
                "viable": len(satisfied_by) >= (requirement.get("minimum") or 0),
            })
    return rows
