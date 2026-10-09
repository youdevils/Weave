"""
Registers the real Assisted operations with ai.services.operations' registry.

    Create     -- one Planning stage: the AI authors a ChangeSet v3 building
                  an initial model from intent + optional evidence; schema
                  changes unrestricted; commits directly once valid; all or
                  nothing (partial_outcome forbidden).
    Reconcile  -- Extraction (claims) -> analysis (deterministic) -> as
                  needed, re-entrantly: Adjudication (decision gaps) / Gap
                  Probe (evidence gaps), each back through analysis ->
                  compile (deterministic) -> Verification (objections back
                  through analysis) -> commit (ai/README.md, "Convergence";
                  corrections bounded per unit of new work, Adjudication /
                  Gap Probe rounds progress-driven, the run bounded
                  overall). Data changes only,
                  compiled by OnyxJar from evidence claims; removal only as
                  retirement on an explicit, confirmed removal claim; intent
                  targets that can be reconciled independently of blocked
                  ones still reach a Proposal (partial_outcome allowed).

Change/Assess are not registered yet; they reuse the same claim pipeline
with their own policies (ai/README.md).
"""

from django.conf import settings

from ai.services.change_set import ALL_ACTION_KINDS, SCHEMA_ACTION_KINDS
from ai.services.operations import DuplicateOperation, OperationDefinition, register_operation
from ai.services.resolution import OperationPolicy
from ai.services.stages.adjudication import AdjudicationStage
from ai.services.stages.extraction import ExtractionCorrectionStage, ExtractionStage
from ai.services.stages.gap_probe import GapProbeCorrectionStage, GapProbeStage
from ai.services.stages.planning import PlanningStage
from ai.services.stages.reading import ReadingPlanStage, ReadingStage
from ai.services.stages.reconcile_steps import AnalysisStage, CompileStage
from ai.services.stages.verification import VerificationStage
from ai.services.workflow.engine import WorkflowDefinition

CREATE_POLICY = OperationPolicy(
    allowed_action_kinds=ALL_ACTION_KINDS - {"delete", "set_active"},
    schema_changes="allowed",
    partial_outcome="forbidden",
)

RECONCILE_POLICY = OperationPolicy(
    allowed_action_kinds=ALL_ACTION_KINDS - {"delete"} - SCHEMA_ACTION_KINDS,
    schema_changes="forbidden",
    partial_outcome="allowed",
)


def build_create_workflow() -> WorkflowDefinition:
    return WorkflowDefinition(
        stages={"planning": PlanningStage()},
        first_stage="planning",
        stage_budgets={"planning": settings.AI_CREATE_PLANNING_MAX_CALLS},
        total_budget=settings.AI_WORKFLOW_MAX_PROVIDER_CALLS,
        explanation_budget=settings.AI_TERMINAL_EXPLANATION_MAX_CALLS,
    )


def build_reconcile_workflow() -> WorkflowDefinition:
    """`AI_RECONCILE_EVIDENCE_MODE` = readings puts the Reading of tables and
    sections (schema-level, ai.services.reconcile.readings) before the
    extraction of prose; claims (the default until the Phase 5 gate) runs the
    legacy per-instance extraction of everything."""

    readings = settings.AI_RECONCILE_EVIDENCE_MODE == "readings"
    reading_stages = {"reading_plan": ReadingPlanStage(), "reading": ReadingStage()} if readings else {}
    reading_budgets = {
        "reading": settings.AI_RECONCILE_READING_MAX_BATCHES,
        "reading_correction": settings.AI_RECONCILE_READING_MAX_CORRECTION_CALLS,
    } if readings else {}
    return WorkflowDefinition(
        stages={
            **reading_stages,
            "extraction": ExtractionStage(),
            "extraction_correction": ExtractionCorrectionStage(),
            "analysis": AnalysisStage(),
            "adjudication": AdjudicationStage(),
            "gap_probe": GapProbeStage(),
            "gap_probe_correction": GapProbeCorrectionStage(),
            "compile": CompileStage(),
            "verification": VerificationStage(),
        },
        first_stage="reading_plan" if readings else "extraction",
        stage_budgets={
            **reading_budgets,
            "extraction": settings.AI_RECONCILE_EXTRACTION_MAX_BATCHES,
            "extraction_correction": settings.AI_RECONCILE_EXTRACTION_MAX_CORRECTION_CALLS,
            # Progress-driven rounds (ai.services.stages.reconcile_steps.route).
            "adjudication": None,
            "adjudication_correction": settings.AI_RECONCILE_ADJUDICATION_MAX_CORRECTION_CALLS,
            "gap_probe": None,
            "gap_probe_correction": settings.AI_RECONCILE_GAP_PROBE_MAX_CORRECTION_CALLS,
            "verification": settings.AI_RECONCILE_VERIFICATION_MAX_CALLS,
            "verification_correction": settings.AI_RECONCILE_VERIFICATION_MAX_CORRECTION_CALLS,
        },
        # One correction opportunity per unit of new work, never per run.
        scoped_budgets={
            "adjudication_correction": "adjudication",
            "gap_probe_correction": "gap_probe",
            "extraction_correction": None,  # per correction wave (ai.services.stages.extraction)
            **({"reading_correction": None} if readings else {}),  # per Reading batch (ai.services.stages.reading)
        },
        total_budget=settings.AI_WORKFLOW_MAX_PROVIDER_CALLS,
        # Readings mode only: scaled with the planned Reading / Extraction
        # workload (reconcile_steps.grant_workload_allowance).
        max_extra_calls=settings.AI_WORKFLOW_MAX_EXTRA_PROVIDER_CALLS if readings else 0,
        explanation_budget=settings.AI_TERMINAL_EXPLANATION_MAX_CALLS,
    )


CREATE = OperationDefinition(
    operation_id="create",
    name="Create",
    description=(
        "builds an initial model structure -- object types, relationship types, attributes, rules, and "
        "optionally example objects and relationships -- from a natural-language intent and optional evidence."
    ),
    evidence="optional",
    can_produce_proposal=True,
    policy=CREATE_POLICY,
    build_workflow=build_create_workflow,
)

RECONCILE = OperationDefinition(
    operation_id="reconcile",
    name="Reconcile",
    description=(
        "reconciles an existing model's canonical state against new intent and supplied evidence, "
        "proposing only the changes that evidence actually supports."
    ),
    evidence="required",
    can_produce_proposal=True,
    policy=RECONCILE_POLICY,
    build_workflow=build_reconcile_workflow,
)


def register_all() -> None:
    for definition in (CREATE, RECONCILE):
        try:
            register_operation(definition)
        except DuplicateOperation:
            pass  # already registered in this process (e.g. autoreload)
