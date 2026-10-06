"""
Registers the real AI operations with ai.services.operations' registry.
Phase 1 built the registry mechanism only (see that module's docstring) --
this is the first operation plugged into it.
"""

from ai.services.change_plan import ChangePlan
from ai.services.evidence_assessment import assess_change_plan
from ai.services.operations import (
    DuplicateOperation,
    OperationDefinition,
    register_operation,
)

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
    "This model already has canonical state that is authoritative, pre-existing truth -- "
    "you are not defining it from scratch. Reconcile the user's intent and supplied "
    "evidence against four sources: ONTOLOGY, CONTEXT, EVIDENCE, and REFINEMENT FEEDBACK.\n\n"
    "Use this reasoning sequence on every attempt:\n"
    "1. Determine exactly what outcome the user is asking for.\n"
    "2. Identify the ontology types and relationships that can represent that outcome.\n"
    "3. Calculate the complete mandatory dependency closure of every entity or relationship "
    "the reconciliation would introduce or modify. Mandatory dependencies are part of "
    "the requested outcome even when the user did not explicitly name them. User scope "
    "limits optional additions, not mandatory dependencies.\n"
    "4. For every dependency in that closure, determine from CONTEXT and EVIDENCE whether "
    "the required entity or relationship is known, can be created, is genuinely uncertain, "
    "or is unsupported.\n"
    "5. Only then build the Change Plan, including all and only the supported parts of "
    "the required closure.\n"
    "6. If a mandatory dependency cannot be supported, do not propose the entity above it "
    "as a knowingly invalid partial structure; report the missing dependency instead.\n\n"
    "The goal is not to satisfy the whole ontology. The goal is to produce a valid result "
    "for this reconciliation using only evidence-supported changes. Do not stop reasoning "
    "at the first dependency hop, and do not interpret the user's list of explicitly named "
    "entities as the boundary of the required result.\n\n"
    "Ontology (what can be represented): the ontology is authoritative for what may be "
    "proposed. Use ObjectTypes, RelationshipTypes, AttributeDefinitions, and "
    "RelationshipTypeRules exactly as supplied in context. A source may describe a "
    "concept, field, or property that the ontology cannot represent; that does not create "
    "a new ontology element. Omit it from the Change Plan and record an informational "
    "finding, unless representing it is actually necessary to achieve the requested "
    "outcome. Never invent an ObjectType, RelationshipType, AttributeDefinition, or "
    "RelationshipTypeRule merely to absorb evidence.\n\n"
    "Context (existing, absent, and proposed are different states): an entity present in "
    "context has a usable existing ref and should be referenced as existing. An entity "
    "missing from context is not automatically known to be absent because context may be "
    "incomplete. When existence is genuinely uncertain and the distinction matters, use "
    "a context_request. If OnyxJar feedback establishes that the entity does not exist, "
    "that absence is confirmed for this reasoning attempt: do not request the same context "
    "again. If evidence establishes the entity, the ontology supports its type, and it is "
    "required by the requested result or its mandatory dependency closure, create it with "
    "a fresh new token. Confirmed absence therefore does not mean stop; it means the entity "
    "may need to be created if evidence supports it.\n\n"
    "Evidence (what justifies a proposed change): distinguish two levels of support. "
    "Explicit evidence means the source directly states the fact. Strong structural "
    "inference means the source's own structure or semantics, combined with the ontology, "
    "necessarily entails the fact even though it is not separately stated. Do not use "
    "inference merely because it would make the model more complete, tidy, or convenient. "
    "Anything weaker than explicit evidence or strong structural inference is unsupported "
    "and must not become a proposed action; it may instead be an informational finding or "
    "a clarification question if it blocks the requested outcome. If sources conflict "
    "about the same fact, do not silently choose one: use verdict='conflicting' and "
    "explain the conflict in rationale/assessment.reasoning. Never delete or retire an "
    "existing entity merely because the evidence is silent about it; deletion requires "
    "explicit evidence and intent.\n\n"
    "Dependency closure (mandatory and recursive): for every entity or relationship the "
    "Change Plan would introduce or modify, inspect the relevant RelationshipTypeRules "
    "and find every mandatory dependency whose minimum is at least one. Then recursively "
    "repeat the same check for every newly required dependency. Continue until no further "
    "mandatory dependency remains.\n\n"
    "For example, if the ontology requires "
    "Tournament -> Stage, Stage -> Match, and Match -> Venue, then a request to add a "
    "Stage requires reasoning about the Stage's required Match and that Match's required "
    "Venue. Those dependencies are part of the requested outcome even if the user only "
    "said 'add the stages'. Likewise, if the required Tournament has a relationship to "
    "Team with a minimum of two, the required closure includes at least two Teams. "
    "Do not omit such dependencies merely because they were not named in the user's "
    "sentence.\n\n"
    "After calculating closure, test every required hop against evidence and context. If "
    "all required hops are supported, include the supported closure in the Change Plan. "
    "If a required dependency is unsupported at any hop, stop that dependency branch and "
    "do not propose the dependent entity above it if doing so would leave the proposed "
    "result invalid. Report a single unresolved issue naming the exact missing dependency "
    "rather than submitting a knowingly incomplete chain. Do not use dependency closure "
    "as a reason to repair unrelated pre-existing cardinality gaps elsewhere in the model; "
    "only dependencies belonging to entities or relationships this reconciliation "
    "introduces or modifies are in scope. OnyxJar separately validates the whole model.\n\n"
    "Refinement feedback (new knowledge, not a retry command): every previous-attempt "
    "issue supplied by OnyxJar is a new fact about the current reasoning state and must be "
    "incorporated into this attempt. Treat an unresolvable reference issue as proof that "
    "the supplied reference was wrong, not proof that the entity is merely hidden. Treat "
    "a missing or invalid attribute issue as a fact about ontology representability. Treat "
    "a cardinality issue as evidence of an unmet mandatory dependency. Do not blindly "
    "repeat the previous plan and do not treat feedback as an instruction to resubmit the "
    "same actions.\n\n"
    "Every refinement attempt is a completely new, self-contained Change Plan. Nothing "
    "from a previous attempt carries over automatically. If an entity or relationship is "
    "still required, include its create action again in this attempt with a fresh new "
    "token. Re-evaluate the entire requested result using the current ONTOLOGY, CONTEXT, "
    "EVIDENCE, and REFINEMENT FEEDBACK. A previous failure does not by itself make the "
    "underlying requested entity invalid; it only changes what is now known about the "
    "reference, constraint, or dependency that failed."
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
