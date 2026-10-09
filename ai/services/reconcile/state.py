"""
ReconcileState: everything a Reconcile run accumulates across stages, kept
explicitly (no provider ever "remembers" anything). The EvidenceGraph and
IntentFrame are claims; `pins` are claimed answers to questions; `retracted`
and `excluded` are Verification's overlays; `dismissals` are coverage
decisions (never claims); the rest is bookkeeping that keeps every loop
bounded and every repeated question/probe/objection from being asked twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ai.services.evidence_graph import EvidenceGraph
from ai.services.intent_frame import IntentFrame


@dataclass
class ReconcileState:
    frame: IntentFrame = field(default_factory=IntentFrame)
    # Requested work whose framing claim could not be grounded in the intent
    # (element id -> {kind, element, reason}): never a claim, never deleted --
    # reported as a block until a Verification frame_error restores it.
    unframed: dict = field(default_factory=dict)
    # element id -> the original elided excerpt, literally repaired to its
    # covering intent span (ai.services.intent_frame.repair_elisions).
    frame_repairs: dict = field(default_factory=dict)
    graph: EvidenceGraph = field(default_factory=EvidenceGraph)
    # question key -> ai.services.reconcile.questions.Pin
    pins: dict = field(default_factory=dict)
    # Evidence ids Verification showed the source does not support.
    retracted: set = field(default_factory=set)
    # Cluster ids / aids Verification objected to as unsupported changes.
    excluded: set = field(default_factory=set)
    # segment id -> {"reason": str, "count": int}: coverage decisions that a
    # segment is not relevant. Never claims; never in the EvidenceGraph.
    dismissals: dict = field(default_factory=dict)
    # requirement id -> "ambiguous" | "not_stated" | "not_stated_contested" | ... (Gap Probe verdicts)
    probe_outcomes: dict = field(default_factory=dict)
    # requirement id -> the labelled evidence (ai.services.reconcile.near_miss)
    # a `not_stated` verdict contradicted: contested, re-probed once.
    probe_contested: dict = field(default_factory=dict)
    # requirement id -> "complete" | "partial" coverage of a not_stated verdict
    missing_evidence: dict = field(default_factory=dict)
    # requirement id -> the claim ids a "found" verdict named.
    probe_claims: dict = field(default_factory=dict)
    probed: set = field(default_factory=set)
    # Requirements re-probed once after an unsupported "found" (never again).
    reprobed: set = field(default_factory=set)
    asked: set = field(default_factory=set)
    objections_seen: set = field(default_factory=set)
    # Latest deterministic results, and the routed WorkQueue
    # (ai.services.stages.reconcile_steps).
    analysis: object = None
    compiled: object = None
    work_queue: object = None

    # -- Readings (ai.services.reconcile.readings; AI_RECONCILE_EVIDENCE_MODE) --
    # "claims" (legacy: per-instance extraction everywhere) | "readings".
    evidence_mode: str = "claims"
    # The request's text (intent links quote it; set by Extraction).
    intent_text: str = ""
    # Every Reading made so far (validated, not_a_table or rejected); their
    # effective form (pins applied) is recomputed by every analysis.
    readings: list = field(default_factory=list)
    # element id -> readings.Element (the slots OnyxJar laid out, and the payload shown).
    reading_elements: dict = field(default_factory=dict)
    reading_batches: list = field(default_factory=list)  # [[element id, ...], ...]
    reading_batch_index: int = 0
    # Segments only a Reading may interpret: no AI claim may cite them
    # (readings.locked_segments); None in claims mode.
    locked_segments: set | None = None
    # What prose extraction may see (readings.prose_eligible); None in claims mode.
    prose_scope: set | None = None

    # -- Extraction batches and their item/segment-level correction ----------
    batches: list = field(default_factory=list)  # [[segment id, ...], ...]
    batch_index: int = 0
    # Segments never sent to Extraction (batch budget spent): uncovered.
    unextracted: set = field(default_factory=set)
    # item id -> (item, [AIIssue]): claims that failed validation, kept out of the graph.
    pending_items: dict = field(default_factory=dict)
    # Intent-frame element ids that failed validation -> issues.
    pending_frame: dict = field(default_factory=dict)
    # Defects awaiting a correction call ([("item"|"frame"|"segment", id)]),
    # and the pack currently being re-asked.
    correction_queue: list = field(default_factory=list)
    current_pack: list = field(default_factory=list)
    # Item / frame / segment ids already re-asked once (never re-asked again).
    reasked: set = field(default_factory=set)
    # Invalid items first produced by a segment re-ask: the next correction
    # wave's queue (their own one correction opportunity).
    next_wave: list = field(default_factory=list)

    question_failures: set = field(default_factory=set)
    probe_failures: set = field(default_factory=set)
    reask_questions: list = field(default_factory=list)
    reask_requirements: list = field(default_factory=list)
    # The current Gap Probe round's evidence packs.
    probe_payloads: dict = field(default_factory=dict)
    # Ids of the `already_extracted` claims the current probe round was shown
    # (a verdict may name those, or claims it emits itself).
    probe_shown_ids: set = field(default_factory=set)
    # requirement id -> (verdict, [AIIssue]): verdicts of the current round
    # that broke the response contract (verdict_claim_missing), awaiting the
    # round's correction.
    verdict_issues: dict = field(default_factory=dict)

    # -- Progress-driven convergence (ai.services.stages.reconcile_steps) ----
    # class ("adjudication" | "gap_probe") -> consecutive rounds without progress.
    idle_rounds: dict = field(default_factory=dict)
    # class -> every work id (question / requirement id) ever routed to it.
    routed_work: dict = field(default_factory=dict)
    # (class, progress marker at its start) of the round in flight, if any.
    round_open: tuple | None = None
    compile_retries: int = 0
    # User-facing notes from Extraction (dropped/unverifiable items).
    notes: list = field(default_factory=list)
    # note message -> the claim id whose ingress fate it restates (shown to
    # Verification as that fate instead of as the note).
    note_refs: dict = field(default_factory=dict)
    # Every claim's ingress fate ({id, local, origin, outcome, reason}) --
    # ai.services.reconcile.ingress; ledgered as `ingest:` decisions.
    ingress_log: list = field(default_factory=list)
    # Global evidence-id allocation (ingress owns ids; never nested prefixes).
    id_counter: int = 0
