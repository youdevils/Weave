"""
Registers the real AI operations with ai.services.operations' registry.
Phase 1 built the registry mechanism only (see that module's docstring) --
this is the first operation plugged into it.
"""

from ai.services.change_plan import ChangePlan
from ai.services.evidence_assessment import assess_change_plan
from ai.services.operations import DuplicateOperation, OperationDefinition, register_operation

CREATE = OperationDefinition(
    operation_id="create",
    name="Assisted Create",
    description=(
        "Creates an initial model structure (object types, relationship "
        "types, rules, and optionally example objects/relationships) from "
        "a natural-language intent and user-supplied evidence."
    ),
    evidence="optional",
    can_produce_proposal=True,
    required_context_categories=frozenset(),
    # Neither field is read anywhere in orchestrator.py/proposal_compiler.py
    # today -- ChangePlan is the de facto placeholder ai.tests.support's
    # fake_operation already uses for both.
    input_schema=ChangePlan,
    output_schema=ChangePlan,
)


RECONCILE_PROMPT_FRAGMENT = (
    "This model already has canonical state that is authoritative, pre-existing truth "
    "-- you are not defining it from scratch. The new evidence/intent describes "
    "information that may or may not require changing it. A new document that simply "
    "doesn't mention an existing entity is never, by itself, evidence that the entity "
    "should be deleted or retired: deletion requires evidence and intent that explicitly "
    "say so. Every candidate action's `assessment.verdict` must honestly reflect whether "
    "its own `evidence` actually supports it; if two supplied sources disagree about the "
    "same fact, never silently pick one -- set verdict='conflicting' and explain both "
    "sides in `rationale`/`assessment.reasoning`, and prefer a context_request or "
    "needs_clarification over guessing. A 'delete' action with no evidence will always "
    "be rejected, regardless of verdict. On a retry, you may simply omit a candidate you "
    "cannot yet adequately support rather than resubmitting it unchanged. "
    "The user specifies the intended outcome; infer concrete model changes from the "
    "existing ontology and supplied evidence wherever reasonably supported, including "
    "creating a clearly evidence-named entity that an existing relationship rule requires "
    "(for example, an explicitly-named parent entity the evidence describes, needed only "
    "to satisfy cardinality) -- do not ask the user to confirm something the evidence "
    "already states plainly. If something needed is missing from context rather than from "
    "the evidence itself, use context_requests to ask OnyxJar for it before considering "
    "clarification. Reserve needs_clarification for a material ambiguity that cannot be "
    "safely resolved from the available context and evidence -- for example, genuinely "
    "conflicting evidence, or a concept the evidence requires that has no reasonable "
    "interpretation in the current model. "
    "Every refinement attempt is a completely new, self-contained Change Plan: nothing you "
    "proposed in a previous attempt carries over automatically, even if OnyxJar's feedback "
    "referred to it -- if you still need an entity you proposed before, include its "
    "'create' action again in this same plan, with a fresh 'new' token, and reference that "
    "token (never the key of its ObjectType or RelationshipType, which only identifies the "
    "type, not a specific instance) from any other action in this same plan that needs it. "
    "An ObjectType's or RelationshipType's own key identifies the type/schema itself, never a "
    "specific instance of it: never use a type's key as an existing-kind EntityRef for an "
    "Object or Relationship, and never put it in a context_request as if it were an instance "
    "you need more context about -- a context_request must name an actual Object or "
    "Relationship instance already present in context. When a type exists but no instance of "
    "it exists yet, and the evidence supports creating one, create that instance with a fresh "
    "'new' token and use the type's key only as that action's parent_ref. If previous-attempt "
    "feedback reports a reference as not existing, treat that as proof the reference itself "
    "was wrong -- most likely a type key used where an instance's ref was needed -- and "
    "correct it; never treat it as evidence the entity exists somewhere just out of reach. "
    "An entity simply not appearing in your current context never by itself means it does not "
    "exist -- context may be incomplete, so when its existence is genuinely uncertain and the "
    "distinction matters, issue a context_request for it instead of guessing. But once OnyxJar's "
    "feedback (a context_request or an existing-reference issue naming it) has established that "
    "the entity does not exist in the model, that absence is now known, confirmed state -- do not "
    "keep treating it as an unresolved external prerequisite or stay blocked on it, and do not "
    "issue another context_request for the same entity again. At that point decide: if the "
    "evidence explicitly establishes the entity, an existing ObjectType covers what it is, and "
    "creating it is necessary to represent the evidence-supported relationships, create it with a "
    "fresh 'new' token in this same Change Plan and reuse that token wherever it is needed; "
    "otherwise, do not invent it -- leave it unresolved or ask for clarification. In short: "
    "uncertainty about whether something exists may call for a context_request; confirmed absence "
    "does not by itself mean stop -- if the evidence establishes the entity and the ontology "
    "supports it, create it. "
    "A Relationship action's parent_ref is always its RelationshipType's own key (for example "
    "\"has_stage\"), never a RelationshipTypeRule's composite ref (for example "
    "\"has_stage:tournament:stage\") even though both appear together in context and the rule's "
    "ref is built from that same RelationshipType key: the RelationshipTypeRule only constrains "
    "which ObjectTypes the relationship may connect and with what cardinality -- useful for "
    "choosing and validating the subject/object endpoints -- but it is never itself the parent of "
    "a Relationship."
)

RECONCILE = OperationDefinition(
    operation_id="reconcile",
    name="Assisted Reconcile",
    description=(
        "Reconciles this model's existing canonical state against new intent and "
        "supplied evidence, proposing only the changes that evidence actually supports."
    ),
    evidence="required",
    can_produce_proposal=True,
    required_context_categories=frozenset(),
    input_schema=ChangePlan,
    output_schema=ChangePlan,
    plan_sufficiency_check=assess_change_plan,
    prompt_fragment=RECONCILE_PROMPT_FRAGMENT,
    # Higher than the global default (settings.AI_MAX_REFINEMENT_CYCLES): Reconcile's
    # loop can fail a cycle for more distinct reasons than Create's (evidence
    # insufficiency/conflict on top of everything Create can already fail on). An
    # initial production value, not a permanent promise -- easy to retune later.
    max_refinement_cycles=5,
)


def register_all() -> None:
    try:
        register_operation(CREATE)
    except DuplicateOperation:
        pass  # already registered in this process (e.g. autoreload)
    try:
        register_operation(RECONCILE)
    except DuplicateOperation:
        pass  # already registered in this process (e.g. autoreload)
