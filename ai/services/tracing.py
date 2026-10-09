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

Size: a provider step also records what the call cost to send
(`call_sizes`: the payload as sent, per top-level section, and the system
prompt and response schema). A deterministic step's Decision Ledger is
written in full only for the run's first ledger and at every `compile`;
the steps between carry a `ledger_delta` against the previous step
(`compact_snapshot`). `load()` expands the deltas, so every reader sees the
full snapshot.

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

from ai.services.provider import AIProvider, ProviderResult, canonical_payload


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


def call_sizes(system_prompt: str, payload: dict, response_schema) -> dict:
    """What one provider call sends, in characters: the payload exactly as
    serialised for the provider, each top-level section of it, the system
    prompt, and the response schema."""

    return {
        "payload_chars": len(canonical_payload(payload)),
        "payload_sections": {key: len(canonical_payload(value)) for key, value in payload.items()},
        "system_prompt_chars": len(system_prompt),
        "schema_chars": len(canonical_payload(response_schema.model_json_schema())),
    }


def compact_snapshot(snapshot: dict, previous: dict | None, *, sequence: int, full: bool = False) -> tuple[dict, dict | None]:
    """-> (the snapshot as written, the ledger the next step diffs against).

    The ledger is written whole when there is nothing to diff against or
    `full` is set; otherwise as `ledger_delta` = {base_sequence, added,
    changed, removed} plus `order` when the decisions' order is not the
    base's order with removals dropped and additions appended."""

    ledger = snapshot.get("ledger")
    if ledger is None:
        return snapshot, previous
    current = {d["decision_id"]: d for d in ledger}
    base = {"sequence": sequence, "decisions": current}
    if previous is None or full:
        return snapshot, base
    before = previous["decisions"]
    delta = {
        "base_sequence": previous["sequence"],
        "added": [d for key, d in current.items() if key not in before],
        "changed": [d for key, d in current.items() if key in before and before[key] != d],
        "removed": [key for key in before if key not in current],
    }
    natural = [key for key in before if key in current] + [d["decision_id"] for d in delta["added"]]
    if natural != list(current):
        delta["order"] = list(current)
    written = {key: value for key, value in snapshot.items() if key != "ledger"}
    written["ledger_delta"] = delta
    return written, base


def expand_snapshots(steps: list[dict]) -> list[dict]:
    """Restores each delta-compacted snapshot's full `ledger`, in sequence
    order (the inverse of `compact_snapshot`)."""

    previous, expanded = None, []
    for step in steps:
        snapshot = step.get("snapshot")
        if isinstance(snapshot, dict) and "ledger" in snapshot:
            previous = {"sequence": step["sequence"], "decisions": {d["decision_id"]: d for d in snapshot["ledger"]}}
        elif isinstance(snapshot, dict) and "ledger_delta" in snapshot:
            delta = snapshot["ledger_delta"]
            if previous is None or previous["sequence"] != delta["base_sequence"]:
                raise ValueError(f"Trace step {step.get('sequence')}: ledger delta has no base step {delta['base_sequence']}.")
            removed = set(delta["removed"])
            decisions = {key: d for key, d in previous["decisions"].items() if key not in removed}
            decisions.update({d["decision_id"]: d for d in delta["changed"]})
            decisions.update({d["decision_id"]: d for d in delta["added"]})
            ordered = {key: decisions[key] for key in (delta.get("order") or list(decisions))}
            restored = {key: value for key, value in snapshot.items() if key != "ledger_delta"}
            restored["ledger"] = list(ordered.values())
            step = {**step, "snapshot": restored}
            previous = {"sequence": step["sequence"], "decisions": ordered}
        expanded.append(step)
    return expanded


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
        "probe_contested": dict(getattr(rs, "probe_contested", {}) or {}),
        "dismissals": dict(rs.dismissals),
        "pins": {k: {"option_id": p.option_id, "basis": p.basis, **({"reason": p.reason} if getattr(p, "reason", "") else {})}
                 for k, p in rs.pins.items()},
        "asked": sorted(rs.asked),
        "probed": sorted(rs.probed),
        "work_queue": rs.work_queue.payload() if getattr(rs, "work_queue", None) is not None else None,
        "unframed": dict(getattr(rs, "unframed", {}) or {}),
        "frame_repairs": dict(getattr(rs, "frame_repairs", {}) or {}),
        "idle_rounds": dict(getattr(rs, "idle_rounds", {}) or {}),
        "verdict_issues": {k: [i.message for i in v[1]] for k, v in (getattr(rs, "verdict_issues", {}) or {}).items()},
    }
    if getattr(rs, "evidence_mode", "claims") == "readings":
        snapshot["readings"] = [r.model_dump(mode="json") for r in getattr(rs, "readings", []) or []]
        snapshot["call_budget"] = dict(getattr(rs, "call_budget", {}) or {})
        snapshot["budget_shortfall"] = dict(getattr(rs, "budget_shortfall", {}) or {})
    if analysis is not None:
        if getattr(analysis, "readings", None):
            snapshot["anomalies"] = [vars(a) for a in analysis.anomalies]
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
    """A run's steps in sequence order, every snapshot with its full ledger."""

    return expand_snapshots([json.loads(p.read_text(encoding="utf-8")) for p in sorted(Path(path).glob("*.json"))])


# -- regression fixtures -------------------------------------------------------------
#
# A raw trace (every payload, snapshot and timing) is a dev artefact; a replay
# FIXTURE keeps, per provider step, only what replay needs: the output, and --
# for the stages replayed by the work they ask for -- that work (`request`),
# distilled from the payload, which is then dropped.

KEYED_STAGES = ("reading", "adjudication", "gap_probe", "extraction_correction", "gap_probe_correction")
FIXTURE_FIELDS = ("kind", "run_id", "sequence", "stage", "attempt", "decision", "schema", "output", "provider_model")


def request_of(stage: str, payload: dict) -> dict:
    """The ids of the work a request asks for: Reading elements, questions,
    requirements, invalid items / frame elements, uncovered segments."""

    if stage == "reading":
        return {"elements": [e["element_id"] for e in payload["elements"]]}
    if stage == "adjudication":
        return {"questions": [q["question_id"] for q in payload["questions"]]}
    if stage == "gap_probe":
        return {"requirements": [r["requirement_id"] for r in payload["requirements"]]}
    if stage == "gap_probe_correction":
        return {"items": [i["id"] for i in payload["invalid_claims"]],
                "requirements": [r["requirement_id"] for r in payload["missing_verdicts"]]
                + [v["requirement"]["requirement_id"] for v in payload["invalid_verdicts"]]}
    return {"items": [i["id"] for i in payload["invalid_items"]], "frame": [i["id"] for i in payload["invalid_frame_items"]],
            "segments": [s["segment"]["segment_id"] for s in payload["uncovered_segments"]]}


def fixture_step(step: dict) -> dict | None:
    """A raw provider step as a replay fixture step (None for anything else)."""

    if step.get("kind") != "provider":
        return None
    fixture = {key: step[key] for key in FIXTURE_FIELDS if key in step}
    if step.get("stage") in KEYED_STAGES and isinstance(step.get("payload"), dict):
        fixture["request"] = request_of(step["stage"], step["payload"])
    return fixture


def capture_fixture(trace_dir, out_dir) -> list[Path]:
    """Every provider step of the raw trace in `trace_dir`, written to
    `out_dir` under its own file name. Returns the files written."""

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []
    for path in sorted(Path(trace_dir).glob("*.json")):
        fixture = fixture_step(json.loads(path.read_text(encoding="utf-8")))
        if fixture is None:
            continue
        target = out / path.name
        target.write_text(json.dumps(fixture, indent=1), encoding="utf-8")
        written.append(target)
    return written


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
