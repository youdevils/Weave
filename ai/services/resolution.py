"""
Deterministic resolution of an AI-facing ChangeSet into OnyxJar's internal,
UUID-based ProposalChange specs (the exact shape
model.services.proposal.proposal.ProposalService.record_changes_bulk takes).

This is where OnyxJar -- not the AI -- decides everything structural about a
ChangeSet before anything is staged: what each semantic reference resolves
to (against SemanticModelIndex, which includes inactive entities), the real
id of every "new" token, the key of every new entity (model.services.keys),
whether the operation's policy permits each action, whether a create would
silently duplicate an existing (or retired) entity, whether attribute values
are representable by the current ontology, and whether every quoted
provenance excerpt really occurs in its cited source. Every problem becomes an
AIIssue naming the offending action_id, never an exception.

It resolves a pure mutation contract (ChangeSet v3) only. Whether an action is
*traced* to the evidence claims that justify it is an evidence-pipeline rule,
checked before resolution (ai.services.reconcile.trace_policy).

Pure with respect to the database: reads only (index + key lookups), writes
nothing. Staging/commit (ai.services.staging) consume the result.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Literal

from django.conf import settings

from model.models.proposal import ProposalChange
from model.services import entity_fields, keys
from model.services.proposal.evidence import (
    LOCATOR_MAX_LENGTH,
    MAX_EVIDENCE_PER_CHANGE,
    NOTE_MAX_LENGTH,
    SOURCE_MAX_LENGTH,
)

from ai.services.artifacts import Finding
from ai.services.change_set import (
    AttributeValue,
    ChangeSet,
    LifecycleTarget,
    ObjectRef,
    RelationshipRef,
    TypeRef,
)
from ai.services.evidence_bundle import EvidenceBundle, source_name
from ai.services.feedback import AIIssue, issue
from ai.services.provenance import check_excerpt
from ai.services.semantic.index import (
    OBJECT_TYPE,
    RELATIONSHIP_TYPE,
    SemanticModelIndex,
    normalize_name,
)

_TARGET_TYPE_BY_KIND = {OBJECT_TYPE: "ObjectType", RELATIONSHIP_TYPE: "RelationshipType"}
_SUGGESTION_LIMIT = 25


@dataclass(frozen=True)
class OperationPolicy:
    """What a given Assisted operation's ChangeSet may contain -- consumed by
    resolve_change_set, never branched on by operation id anywhere."""

    allowed_action_kinds: frozenset
    # forbidden: no schema actions; allowed: unrestricted (Create).
    schema_changes: Literal["forbidden", "allowed"]
    # allowed: intent targets that can be reconciled independently of a
    # blocked target still reach a Proposal (the blocked ones become material
    # findings); forbidden: any blocked target means no Proposal at all.
    partial_outcome: Literal["allowed", "forbidden"] = "forbidden"

    def describe(self) -> dict:
        return {
            "allowed_action_kinds": sorted(self.allowed_action_kinds),
            "schema_changes": self.schema_changes,
            "partial_outcome": self.partial_outcome,
        }


@dataclass
class Minted:
    """An entity this ChangeSet creates: OnyxJar's id/key for it, and enough
    about it to resolve later references and attribute feedback."""

    uuid: str
    domain: str  # object_type | relationship_type | attribute | object | relationship | rule
    action_id: str
    token: str | None = None
    name: str = ""
    # object -> its ObjectType id; attribute -> its owner type id; relationship -> its RelationshipType id
    parent_id: str | None = None
    owner_kind: str | None = None
    data_type: str | None = None
    choices: tuple = ()
    key: str | None = None


@dataclass
class RefMap:
    minted: dict[str, Minted] = field(default_factory=dict)  # uuid -> Minted
    tokens: dict[str, Minted] = field(default_factory=dict)  # token -> Minted


@dataclass(frozen=True)
class Touched:
    target_type: str
    target_id: str
    action_id: str
    change: str  # created | updated | retired | reactivated | deleted


@dataclass
class Resolution:
    specs: list[dict] = field(default_factory=list)
    action_ranges: list[tuple[str, int, int]] = field(default_factory=list)
    evidence: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)
    ref_map: RefMap = field(default_factory=RefMap)
    touched: list[Touched] = field(default_factory=list)
    issues: list[AIIssue] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues


def resolve_change_set(
    change_set: ChangeSet,
    *,
    model,
    index: SemanticModelIndex,
    policy: OperationPolicy,
    bundle: EvidenceBundle | None = None,
    intent_text: str = "",
) -> Resolution:
    return _Resolver(change_set, model, index, policy, bundle or EvidenceBundle(), intent_text).run()


class _Resolver:

    def __init__(self, change_set, model, index, policy, bundle, intent_text=""):
        self.change_set = change_set
        self.model = model
        self.index = index
        self.policy = policy
        self.bundle = bundle
        self.intent_text = intent_text
        self.result = Resolution()
        self.ref_map = self.result.ref_map
        self.specs_by_action: dict[str, list[dict]] = {}
        self.claimed_keys: dict[tuple, set] = {}
        self.reactivated: set[str] = set()  # canonical ids set_active(true) in this ChangeSet
        self.set_rule_triples: set[tuple[str, str, str]] = set()
        self.set_relationship_triples: set[tuple[str, str, str]] = set()
        self.set_object_names: set[tuple[str, str]] = set()

    # -- helpers ---------------------------------------------------------

    def fail(self, code, message, *, action_id=None, ref=None, field=None):
        self.result.issues.append(issue(code, message, action_id=action_id, ref=ref, field=field))

    def emit(self, action_id, spec):
        self.specs_by_action.setdefault(action_id, []).append(spec)

    def touch(self, target_type, target_id, action_id, change):
        self.result.touched.append(Touched(target_type, str(target_id), action_id, change))

    def key_for(self, target_type, name, *, parent_type=None, parent_id=None):
        scope = (target_type, parent_type, str(parent_id) if parent_id else None)
        used = self.claimed_keys.setdefault(scope, set())
        key = keys.generate_key(
            target_type,
            name or "",
            model=self.model,
            proposal=None,
            parent_type=parent_type,
            parent_id=parent_id,
            also_used=used,
        )
        used.add(key)
        return key

    def _type_keys(self, kind):
        pool = self.index.object_types if kind == OBJECT_TYPE else self.index.relationship_types
        return sorted(t.key for t in pool.values())[:_SUGGESTION_LIMIT]

    def label(self, kind):
        return "ObjectType" if kind == OBJECT_TYPE else "RelationshipType"

    # -- reference resolution ------------------------------------------------

    def resolve_type(self, ref: TypeRef, kind: str, action_id: str, field_name: str) -> str | None:
        if ref.kind == "existing":
            if not ref.key:
                self.fail("malformed_reference", f"{field_name}: an existing {self.label(kind)} reference needs `key`.", action_id=action_id, field=field_name)
                return None
            item = self.index.type_by_key(kind, ref.key)
            if item is None:
                self.fail(
                    "unresolvable_reference",
                    f"{field_name}: no {self.label(kind)} with key '{ref.key}'. "
                    f"Existing {self.label(kind)} keys: {', '.join(self._type_keys(kind)) or '(none)'}.",
                    action_id=action_id,
                    field=field_name,
                )
                return None
            return item.id

        if not ref.token:
            self.fail("malformed_reference", f"{field_name}: a new reference needs `token`.", action_id=action_id, field=field_name)
            return None
        minted = self.ref_map.tokens.get(ref.token)
        if minted is None:
            self.fail("dangling_token", f"{field_name}: token '{ref.token}' is not created by any action in this ChangeSet.", action_id=action_id, field=field_name)
            return None
        if minted.domain != kind:
            self.fail(
                "token_kind_mismatch",
                f"{field_name}: token '{ref.token}' is a {minted.domain}, not a {kind}.",
                action_id=action_id,
                field=field_name,
            )
            return None
        return minted.uuid

    def resolve_object(self, ref: ObjectRef, action_id: str, field_name: str):
        """-> (object_id, object_type_id, IObject|None) or (None, None, None)."""

        if ref.kind == "existing":
            if not (ref.type_key and ref.key):
                self.fail("malformed_reference", f"{field_name}: an existing Object reference needs `type_key` and `key`.", action_id=action_id, field=field_name)
                return None, None, None
            object_type = self.index.object_type_by_key(ref.type_key)
            if object_type is None:
                self.fail(
                    "unresolvable_reference",
                    f"{field_name}: no ObjectType with key '{ref.type_key}'. "
                    f"Existing ObjectType keys: {', '.join(self._type_keys(OBJECT_TYPE)) or '(none)'}.",
                    action_id=action_id,
                    field=field_name,
                )
                return None, None, None
            obj = self.index.object_by_key(object_type.id, ref.key)
            if obj is None:
                near = self.index.match_objects(object_type.id, ref.key.replace("_", " "))
                hint = (
                    " Did you mean: " + ", ".join(f"{ref.type_key}:{m.object.key} ('{m.object.name}')" for m in near[:5]) + "?"
                    if near
                    else " If it should exist, create it with a new token; otherwise omit it."
                )
                self.fail(
                    "unresolvable_reference",
                    f"{field_name}: no {object_type.name} with key '{ref.key}'.{hint}",
                    action_id=action_id,
                    field=field_name,
                )
                return None, None, None
            return obj.id, obj.type_id, obj

        if not ref.token:
            self.fail("malformed_reference", f"{field_name}: a new Object reference needs `token`.", action_id=action_id, field=field_name)
            return None, None, None
        minted = self.ref_map.tokens.get(ref.token)
        if minted is None:
            self.fail("dangling_token", f"{field_name}: token '{ref.token}' is not created by any action in this ChangeSet.", action_id=action_id, field=field_name)
            return None, None, None
        if minted.domain != "object":
            self.fail("token_kind_mismatch", f"{field_name}: token '{ref.token}' is a {minted.domain}, not an object.", action_id=action_id, field=field_name)
            return None, None, None
        return minted.uuid, minted.parent_id, None

    def resolve_relationship(self, ref: RelationshipRef, action_id: str, field_name: str):
        relationship_type = self.index.relationship_type_by_key(ref.relationship_type_key)
        if relationship_type is None:
            self.fail(
                "unresolvable_reference",
                f"{field_name}: no RelationshipType with key '{ref.relationship_type_key}'.",
                action_id=action_id,
                field=field_name,
            )
            return None
        if ref.subject.kind != "existing" or ref.object.kind != "existing":
            self.fail(
                "malformed_reference",
                f"{field_name}: an existing Relationship is identified by existing subject and object Objects.",
                action_id=action_id,
                field=field_name,
            )
            return None
        subject_id, _, _ = self.resolve_object(ref.subject, action_id, f"{field_name}.subject")
        object_id, _, _ = self.resolve_object(ref.object, action_id, f"{field_name}.object")
        if subject_id is None or object_id is None:
            return None
        matches = self.index.relationships_matching(relationship_type.id, subject_id, object_id)
        if not matches:
            self.fail(
                "unresolvable_reference",
                f"{field_name}: no '{ref.relationship_type_key}' relationship from "
                f"{ref.subject.type_key}:{ref.subject.key} to {ref.object.type_key}:{ref.object.key} exists.",
                action_id=action_id,
                field=field_name,
            )
            return None
        if len(matches) > 1:
            described = "; ".join(
                f"attributes={m.attributes}, valid_from={m.valid_from}, valid_to={m.valid_to}, active={m.is_active}"
                for m in matches[:5]
            )
            self.fail(
                "ambiguous_relationship_reference",
                f"{field_name}: {len(matches)} matching '{ref.relationship_type_key}' relationships exist "
                f"between these Objects ({described}); it cannot be identified unambiguously -- omit this change.",
                action_id=action_id,
                field=field_name,
            )
            return None
        return matches[0]

    def resolve_lifecycle(self, target: LifecycleTarget, action_id: str):
        """-> (target_type, canonical id, is_active now) or None."""

        entity = target.entity
        if entity == "object":
            if target.object is None or target.object.kind != "existing":
                self.fail("malformed_reference", "target.object must be an existing Object reference.", action_id=action_id, field="target")
                return None
            object_id, _, obj = self.resolve_object(target.object, action_id, "target.object")
            return ("Object", object_id, obj.is_active) if obj else None
        if entity == "relationship":
            if target.relationship is None:
                self.fail("malformed_reference", "target.relationship is required.", action_id=action_id, field="target")
                return None
            relationship = self.resolve_relationship(target.relationship, action_id, "target.relationship")
            return ("Relationship", relationship.id, relationship.is_active) if relationship else None
        if entity in (OBJECT_TYPE, RELATIONSHIP_TYPE):
            item = self.index.type_by_key(entity, target.type_key) if target.type_key else None
            if item is None:
                self.fail("unresolvable_reference", f"target.type_key: no {self.label(entity)} with key '{target.type_key}'.", action_id=action_id, field="target")
                return None
            return (_TARGET_TYPE_BY_KIND[entity], item.id, item.is_active)
        if entity == "attribute":
            ref = target.attribute
            owner = self.index.type_by_key(ref.owner_kind, ref.owner_key) if ref else None
            attribute = self.index.attribute(owner.id, ref.key) if owner else None
            if attribute is None:
                self.fail("unresolvable_reference", "target.attribute does not name an existing AttributeDefinition.", action_id=action_id, field="target")
                return None
            return ("AttributeDefinition", attribute.id, attribute.is_active)
        return None

    # -- attribute values ------------------------------------------------

    def resolve_attribute_values(self, values: list[AttributeValue], owner_id: str | None, action_id: str) -> dict | None:
        if owner_id is None:
            return None
        resolved: dict = {}
        ok = True
        for position, value in enumerate(values):
            field_name = f"attributes[{position}]"
            if value.set_variants() > 1:
                self.fail("ambiguous_attribute_value", f"{field_name}: set exactly one of string_value/number_value/boolean_value.", action_id=action_id, field=field_name)
                ok = False
                continue

            if value.attribute_token:
                minted = self.ref_map.tokens.get(value.attribute_token)
                if minted is None or minted.domain != "attribute" or minted.parent_id != owner_id:
                    self.fail(
                        "unresolvable_reference",
                        f"{field_name}: attribute_token '{value.attribute_token}' is not an attribute this ChangeSet creates on this entity's type.",
                        action_id=action_id,
                        field=field_name,
                    )
                    ok = False
                    continue
                key, data_type, choices = minted.key, minted.data_type, list(minted.choices)
            elif value.key:
                attribute = self.index.attribute(owner_id, value.key)
                if attribute is None:
                    available = [a.key for a in self.index.attributes_of(owner_id) if a.is_active]
                    self.fail(
                        "attribute_not_defined",
                        f"{field_name}: this type has no attribute '{value.key}'. Defined attributes: "
                        f"{', '.join(available) or '(none)'}. Evidence facts are not model fields -- omit the "
                        "value unless the attribute genuinely exists.",
                        action_id=action_id,
                        field=field_name,
                    )
                    ok = False
                    continue
                if not attribute.is_active and attribute.id not in self.reactivated:
                    self.fail("inactive_entity", f"{field_name}: attribute '{value.key}' is retired (inactive).", action_id=action_id, field=field_name)
                    ok = False
                    continue
                key, data_type, choices = attribute.key, attribute.data_type, attribute.choices
            else:
                self.fail("malformed_attribute_value", f"{field_name}: needs `key` or `attribute_token`.", action_id=action_id, field=field_name)
                ok = False
                continue

            if key in resolved:
                self.fail("duplicate_attribute", f"{field_name}: attribute '{key}' is set more than once.", action_id=action_id, field=field_name)
                ok = False
                continue

            native = value.native()
            if native is not None:
                if data_type == "number" and value.number_value is None:
                    self.fail("attribute_value_type_mismatch", f"{field_name}: '{key}' is a number attribute; use number_value.", action_id=action_id, field=field_name)
                    ok = False
                    continue
                if data_type == "boolean" and value.boolean_value is None:
                    self.fail("attribute_value_type_mismatch", f"{field_name}: '{key}' is a boolean attribute; use boolean_value.", action_id=action_id, field=field_name)
                    ok = False
                    continue
                if data_type not in ("number", "boolean") and value.string_value is None:
                    self.fail("attribute_value_type_mismatch", f"{field_name}: '{key}' is a {data_type} attribute; use string_value.", action_id=action_id, field=field_name)
                    ok = False
                    continue
                if data_type == "choice" and choices and native not in choices:
                    self.fail(
                        "attribute_value_not_a_choice",
                        f"{field_name}: '{native}' is not one of {', '.join(map(str, choices))} for '{key}'.",
                        action_id=action_id,
                        field=field_name,
                    )
                    ok = False
                    continue
            resolved[key] = native
        return resolved if ok else None

    # -- policy / provenance -------------------------------------------------

    def check_schema_policy(self, action) -> None:
        if self.policy.schema_changes == "forbidden":
            self.fail("schema_change_not_allowed", "This operation may not change the model's schema.", action_id=action.action_id)

    def check_provenance(self, action) -> None:
        """Every quoted excerpt the action carries must occur in its cited source."""

        issues: list[AIIssue] = []
        for position, item in enumerate(action.provenance):
            check_excerpt(
                item.source_id, item.excerpt, item_id=None, where=f"provenance[{position}]",
                bundle=self.bundle, intent_text=self.intent_text, issues=issues,
            )
        for found in issues:
            self.fail(found.code, found.message, action_id=action.action_id, field="provenance")

    # -- evidence ----------------------------------------------------------

    def evidence_for(self, action) -> list[tuple[str, str, str]]:
        items: list[tuple[str, str, str]] = []
        if action.rationale.strip():
            items.append(("AI", "", action.rationale.strip()[:NOTE_MAX_LENGTH]))

        seen = set()
        for item in action.provenance:
            entry = (
                source_name(self.bundle, item.source_id)[:SOURCE_MAX_LENGTH] or "Evidence",
                (item.locator or "")[:LOCATOR_MAX_LENGTH],
                (item.excerpt or "")[:NOTE_MAX_LENGTH],
            )
            if entry in seen:
                continue
            seen.add(entry)
            items.append(entry)
        return items[:MAX_EVIDENCE_PER_CHANGE]

    # -- spec builders ---------------------------------------------------------

    def create_spec(self, target_type, target_id, parent_type, parent_id, after):
        bad = entity_fields.illegal_fields(target_type, after.keys(), operation="create")
        return bad, {
            "operation": ProposalChange.Operation.CREATE,
            "target_type": target_type,
            "target_id": uuid.UUID(str(target_id)),
            "parent_type": parent_type,
            "parent_id": uuid.UUID(str(parent_id)) if parent_id else None,
            "before": None,
            "after": after,
        }

    def update_spec(self, target_type, target_id, field_name, before, after):
        return {
            "operation": ProposalChange.Operation.UPDATE,
            "target_type": target_type,
            "target_id": uuid.UUID(str(target_id)),
            "parent_type": "",
            "parent_id": None,
            "before": {"field": field_name, "value": before},
            "after": {"field": field_name, "value": after},
        }

    def emit_create(self, action, target_type, target_id, parent_type, parent_id, after):
        bad, spec = self.create_spec(target_type, target_id, parent_type, parent_id, after)
        if bad:
            self.fail("invalid_field", f"{target_type} has no field(s): {', '.join(sorted(bad))}.", action_id=action.action_id)
            return
        self.emit(action.action_id, spec)
        self.touch(target_type, target_id, action.action_id, "created")

    def emit_updates(self, action, target_type, target_id, changes: dict, current: dict):
        emitted = False
        for field_name, value in changes.items():
            if current.get(field_name) == value and not field_name.startswith("attributes."):
                continue
            self.emit(action.action_id, self.update_spec(target_type, target_id, field_name, current.get(field_name), value))
            emitted = True
        if not emitted:
            self.fail("empty_update", "This update changes nothing; omit it.", action_id=action.action_id)
            return
        self.touch(target_type, target_id, action.action_id, "updated")

    # -- the passes --------------------------------------------------------------

    def run(self) -> Resolution:
        actions = list(self.change_set.actions)

        if len(actions) > settings.AI_MAX_CHANGE_SET_ACTIONS:
            self.fail("change_set_too_large", f"A ChangeSet may contain at most {settings.AI_MAX_CHANGE_SET_ACTIONS} actions.")

        seen_ids = set()
        for action in actions:
            if not action.action_id.strip():
                self.fail("malformed_action", "Every action needs a non-empty action_id.")
            elif action.action_id in seen_ids:
                self.fail("duplicate_action_id", f"action_id '{action.action_id}' is used more than once.", action_id=action.action_id)
            seen_ids.add(action.action_id)
            if action.kind not in self.policy.allowed_action_kinds:
                hint = " Use set_active(active=false) to retire instead." if action.kind == "delete" else ""
                self.fail("action_not_allowed", f"This operation may not use '{action.kind}' actions.{hint}", action_id=action.action_id)

        self.mint_tokens(actions)
        for action in actions:
            if action.kind == "set_active" and action.active:
                target = self.resolve_lifecycle(action.target, action.action_id)
                if target:
                    self.reactivated.add(str(target[1]))

        order = (
            "create_type", "update_type", "create_attribute", "update_attribute", "create_rule",
            "update_rule", "create_object", "update_object", "create_relationship",
            "update_relationship", "set_active", "delete",
        )
        for kind in order:
            for action in actions:
                if action.kind != kind or action.kind not in self.policy.allowed_action_kinds:
                    continue
                getattr(self, f"do_{kind}")(action)


        for action in actions:
            specs = self.specs_by_action.get(action.action_id, [])
            start = len(self.result.specs)
            self.result.specs.extend(specs)
            if specs:
                self.result.action_ranges.append((action.action_id, start, len(self.result.specs)))
                self.result.evidence[action.action_id] = self.evidence_for(action)
        return self.result

    def mint_tokens(self, actions) -> None:
        for action in actions:
            if action.kind == "create_type":
                domain = action.type_kind
            elif action.kind == "create_attribute":
                domain = "attribute"
            elif action.kind == "create_object":
                domain = "object"
            else:
                continue
            token = (action.token or "").strip()
            if not token:
                self.fail("malformed_action", f"A {action.kind} action needs a token.", action_id=action.action_id)
                continue
            if token in self.ref_map.tokens:
                self.fail("duplicate_token", f"Token '{token}' is created by more than one action.", action_id=action.action_id)
                continue
            minted = Minted(uuid=str(uuid.uuid4()), domain=domain, action_id=action.action_id, token=token, name=action.name)
            self.ref_map.tokens[token] = minted
            self.ref_map.minted[minted.uuid] = minted

    # schema ------------------------------------------------------------

    def do_create_type(self, action):
        minted = self.ref_map.tokens.get(action.token)
        if minted is None or minted.action_id != action.action_id:
            return
        self.check_schema_policy(action)
        self.check_provenance(action)
        existing = self.index.types_named(action.type_kind, action.name)
        if existing:
            item = existing[0]
            state = "a retired (inactive) " if not item.is_active else "an "
            hint = " Reactivate it with set_active instead." if not item.is_active else " Reference it as existing instead."
            self.fail(
                "probable_duplicate_of_existing",
                f"{state}{self.label(action.type_kind)} '{item.name}' (key '{item.key}') already exists.{hint}",
                action_id=action.action_id,
                ref={"entity": action.type_kind, "key": item.key, "active": item.is_active},
            )
            return
        target_type = _TARGET_TYPE_BY_KIND[action.type_kind]
        minted.key = self.key_for(target_type, action.name)
        self.emit_create(
            action, target_type, minted.uuid, "Model", self.model.id,
            {"name": action.name, "description": action.description, "key": minted.key},
        )

    def do_update_type(self, action):
        self.check_schema_policy(action)
        self.check_provenance(action)
        item = self.index.type_by_key(action.type_kind, action.key)
        if item is None:
            self.fail("unresolvable_reference", f"key: no {self.label(action.type_kind)} with key '{action.key}'.", action_id=action.action_id)
            return
        changes = {k: v for k, v in (("name", action.name), ("description", action.description)) if v is not None}
        self.emit_updates(action, _TARGET_TYPE_BY_KIND[action.type_kind], item.id, changes, {"name": item.name, "description": item.description})

    def do_create_attribute(self, action):
        minted = self.ref_map.tokens.get(action.token)
        if minted is None or minted.action_id != action.action_id:
            return
        self.check_schema_policy(action)
        self.check_provenance(action)
        owner_id = self.resolve_type(action.owner, action.owner_kind, action.action_id, "owner")
        if owner_id is None:
            return
        wanted = normalize_name(action.name)
        for attribute in self.index.attributes_of(owner_id):
            if normalize_name(attribute.name) == wanted or attribute.key == keys.slugify_key(action.name):
                self.fail(
                    "probable_duplicate_of_existing",
                    f"This type already has attribute '{attribute.key}' ('{attribute.name}'"
                    f"{', retired' if not attribute.is_active else ''}).",
                    action_id=action.action_id,
                )
                return
        config = action.config.to_dict()
        if action.data_type == "choice" and not config.get("choices"):
            self.fail("invalid_attribute_definition", "A choice attribute needs config.choices.", action_id=action.action_id)
            return
        parent_type = _TARGET_TYPE_BY_KIND[action.owner_kind]
        minted.parent_id = owner_id
        minted.owner_kind = action.owner_kind
        minted.data_type = action.data_type
        minted.choices = tuple(config.get("choices") or ())
        minted.key = self.key_for("AttributeDefinition", action.name, parent_type=parent_type, parent_id=owner_id)
        self.emit_create(
            action, "AttributeDefinition", minted.uuid, parent_type, owner_id,
            {
                "name": action.name, "data_type": action.data_type, "description": action.description,
                "required": action.required, "nullable": action.nullable, "config": config, "key": minted.key,
            },
        )

    def do_update_attribute(self, action):
        self.check_schema_policy(action)
        self.check_provenance(action)
        owner = self.index.type_by_key(action.target.owner_kind, action.target.owner_key)
        attribute = self.index.attribute(owner.id, action.target.key) if owner else None
        if attribute is None:
            self.fail("unresolvable_reference", "target does not name an existing AttributeDefinition.", action_id=action.action_id)
            return
        changes = {
            k: v
            for k, v in (
                ("name", action.name), ("description", action.description), ("required", action.required),
                ("nullable", action.nullable), ("config", action.config.to_dict() if action.config else None),
            )
            if v is not None
        }
        current = {
            "name": attribute.name, "description": attribute.description, "required": attribute.required,
            "nullable": attribute.nullable, "config": attribute.config,
        }
        self.emit_updates(action, "AttributeDefinition", attribute.id, changes, current)

    def do_create_rule(self, action):
        relationship_type_id = self.resolve_type(action.relationship_type, RELATIONSHIP_TYPE, action.action_id, "relationship_type")
        subject_type_id = self.resolve_type(action.subject_type, OBJECT_TYPE, action.action_id, "subject_type")
        object_type_id = self.resolve_type(action.object_type, OBJECT_TYPE, action.action_id, "object_type")
        self.check_schema_policy(action)
        self.check_provenance(action)
        if None in (relationship_type_id, subject_type_id, object_type_id):
            return
        triple = (relationship_type_id, subject_type_id, object_type_id)
        if self.index.rule(*triple) is not None or triple in self.set_rule_triples:
            self.fail("rule_already_exists", "A rule for this relationship type and subject/object type pair already exists.", action_id=action.action_id)
            return
        self.set_rule_triples.add(triple)
        rule_id = str(uuid.uuid4())
        self.ref_map.minted[rule_id] = Minted(uuid=rule_id, domain="rule", action_id=action.action_id)
        self.emit_create(
            action, "RelationshipTypeRule", rule_id, "RelationshipType", relationship_type_id,
            {
                "subject_type_id": subject_type_id,
                "object_type_id": object_type_id,
                "subject_minimum": action.subjects_per_object.minimum,
                "subject_maximum": action.subjects_per_object.maximum,
                "object_minimum": action.objects_per_subject.minimum,
                "object_maximum": action.objects_per_subject.maximum,
            },
        )

    def do_update_rule(self, action):
        self.check_schema_policy(action)
        self.check_provenance(action)
        relationship_type = self.index.relationship_type_by_key(action.target.relationship_type_key)
        subject_type = self.index.object_type_by_key(action.target.subject_type_key)
        object_type = self.index.object_type_by_key(action.target.object_type_key)
        rule = (
            self.index.rule(relationship_type.id, subject_type.id, object_type.id)
            if relationship_type and subject_type and object_type
            else None
        )
        if rule is None:
            self.fail("unresolvable_reference", "target does not name an existing RelationshipTypeRule.", action_id=action.action_id)
            return
        changes = {
            "subject_minimum": action.subjects_per_object.minimum,
            "subject_maximum": action.subjects_per_object.maximum,
            "object_minimum": action.objects_per_subject.minimum,
            "object_maximum": action.objects_per_subject.maximum,
        }
        current = {k: getattr(rule, k) for k in changes}
        self.emit_updates(action, "RelationshipTypeRule", rule.id, changes, current)

    # data --------------------------------------------------------------

    def do_create_object(self, action):
        minted = self.ref_map.tokens.get(action.token)
        if minted is None or minted.action_id != action.action_id:
            return
        self.check_provenance(action)
        type_id = self.resolve_type(action.type, OBJECT_TYPE, action.action_id, "type")
        if type_id is None:
            return
        minted.parent_id = type_id
        object_type = self.index.object_types.get(type_id)
        if object_type is not None and not object_type.is_active and type_id not in self.reactivated:
            self.fail(
                "inactive_entity",
                f"ObjectType '{object_type.key}' is retired (inactive); reactivate it with set_active (if "
                "justified) or omit this object.",
                action_id=action.action_id,
            )
            return

        name_marker = (type_id, normalize_name(action.name))
        if name_marker in self.set_object_names:
            self.fail("duplicate_in_change_set", f"'{action.name}' is created more than once.", action_id=action.action_id)
            return
        self.set_object_names.add(name_marker)

        if object_type is not None and not action.confirmed_distinct:
            matches = self.index.match_objects(type_id, action.name)
            if matches:
                described = ", ".join(
                    f"{object_type.key}:{m.object.key} ('{m.object.name}'{', retired' if not m.object.is_active else ''})"
                    for m in matches[:5]
                )
                retired = any(not m.object.is_active for m in matches)
                hint = (
                    " Reference it as existing (update it if the evidence changes it), reactivate a retired one "
                    "with set_active, or set confirmed_distinct only if it is genuinely a different entity."
                )
                self.fail(
                    "inactive_entity" if retired and all(not m.object.is_active for m in matches) else "probable_duplicate_of_existing",
                    f"An existing {object_type.name} matches '{action.name}': {described}.{hint}",
                    action_id=action.action_id,
                    ref=self.index.object_identity(matches[0].object),
                )
                return

        attributes = self.resolve_attribute_values(action.attributes, type_id, action.action_id)
        if attributes is None:
            return
        minted.key = self.key_for("Object", action.name, parent_type="ObjectType", parent_id=type_id)
        after = {"name": action.name, "description": action.description, "key": minted.key}
        if attributes:
            after["attributes"] = attributes
        self.emit_create(action, "Object", minted.uuid, "ObjectType", type_id, after)

    def do_update_object(self, action):
        self.check_provenance(action)
        if action.target.kind != "existing":
            self.fail("malformed_reference", "update_object targets an existing Object only.", action_id=action.action_id)
            return
        object_id, type_id, obj = self.resolve_object(action.target, action.action_id, "target")
        if obj is None:
            return
        if not obj.is_active and obj.id not in self.reactivated:
            self.fail("inactive_entity", f"'{obj.name}' is retired (inactive); reactivate it with set_active first if the evidence supports it.", action_id=action.action_id)
            return
        attributes = self.resolve_attribute_values(action.attributes, type_id, action.action_id)
        if attributes is None:
            return
        changes = {k: v for k, v in (("name", action.name), ("description", action.description)) if v is not None}
        current = {"name": obj.name, "description": obj.description}
        for key, value in attributes.items():
            if obj.attributes.get(key) == value:
                continue
            changes[f"attributes.{key}"] = value
            current[f"attributes.{key}"] = obj.attributes.get(key)
        self.emit_updates(action, "Object", object_id, changes, current)

    def _endpoint_active(self, object_id, action, field_name) -> bool:
        obj = self.index.objects.get(object_id)
        if obj is not None and not obj.is_active and obj.id not in self.reactivated:
            self.fail(
                "inactive_entity",
                f"{field_name}: '{obj.name}' is retired (inactive); reactivate it with set_active first if the "
                "evidence supports it.",
                action_id=action.action_id,
                field=field_name,
            )
            return False
        return True

    def do_create_relationship(self, action):
        self.check_provenance(action)
        relationship_type_id = self.resolve_type(action.relationship_type, RELATIONSHIP_TYPE, action.action_id, "relationship_type")
        subject_id, subject_type_id, _ = self.resolve_object(action.subject, action.action_id, "subject")
        object_id, object_type_id, _ = self.resolve_object(action.object, action.action_id, "object")
        if None in (relationship_type_id, subject_id, object_id, subject_type_id, object_type_id):
            return  # the unresolved part has already been reported

        relationship_type = self.index.relationship_types.get(relationship_type_id)
        if relationship_type is not None and not relationship_type.is_active and relationship_type_id not in self.reactivated:
            self.fail("inactive_entity", f"RelationshipType '{relationship_type.key}' is retired (inactive).", action_id=action.action_id)
            return
        if not (self._endpoint_active(subject_id, action, "subject") and self._endpoint_active(object_id, action, "object")):
            return

        triple_types = (relationship_type_id, subject_type_id, object_type_id)
        if self.index.rule(*triple_types) is None and triple_types not in self.set_rule_triples:
            allowed = []
            if relationship_type is not None:
                for rule in self.index.rules_of(relationship_type_id):
                    allowed.append(
                        f"{self.index.object_types[rule.subject_type_id].key} -> {self.index.object_types[rule.object_type_id].key}"
                    )
            subject_label = self._type_label(subject_type_id)
            object_label = self._type_label(object_type_id)
            self.fail(
                "no_matching_rule",
                f"No rule allows this relationship type from {subject_label} to {object_label}. "
                f"Allowed: {', '.join(allowed) or '(none defined)'}. Check the direction (subject/object).",
                action_id=action.action_id,
            )
            return

        triple = (relationship_type_id, subject_id, object_id)
        if not action.confirmed_distinct:
            if triple in self.set_relationship_triples:
                self.fail("duplicate_in_change_set", "This relationship is created more than once.", action_id=action.action_id)
                return
            existing = self.index.relationships_matching(*triple)
            if existing:
                retired = all(not r.is_active for r in existing)
                self.fail(
                    "relationship_already_exists",
                    "This relationship already exists"
                    + (" but is retired; reactivate it with set_active if the evidence supports it." if retired else "; no create is needed."),
                    action_id=action.action_id,
                )
                return
        self.set_relationship_triples.add(triple)

        attributes = self.resolve_attribute_values(action.attributes, relationship_type_id, action.action_id)
        if attributes is None:
            return
        relationship_id = str(uuid.uuid4())
        self.ref_map.minted[relationship_id] = Minted(
            uuid=relationship_id, domain="relationship", action_id=action.action_id, parent_id=relationship_type_id
        )
        after = {"subject_id": str(subject_id), "object_id": str(object_id)}
        if attributes:
            after["attributes"] = attributes
        if action.valid_from:
            after["valid_from"] = action.valid_from
        if action.valid_to:
            after["valid_to"] = action.valid_to
        self.emit_create(action, "Relationship", relationship_id, "RelationshipType", relationship_type_id, after)

    def _type_label(self, type_id):
        item = self.index.object_types.get(type_id)
        if item is not None:
            return f"'{item.key}'"
        minted = self.ref_map.minted.get(type_id)
        return f"new type '{minted.token}'" if minted else "an unknown type"

    def do_update_relationship(self, action):
        self.check_provenance(action)
        relationship = self.resolve_relationship(action.target, action.action_id, "target")
        if relationship is None:
            return
        if not relationship.is_active and relationship.id not in self.reactivated:
            self.fail("inactive_entity", "This relationship is retired (inactive); reactivate it first if the evidence supports it.", action_id=action.action_id)
            return
        attributes = self.resolve_attribute_values(action.attributes, relationship.type_id, action.action_id)
        if attributes is None:
            return
        changes = {k: v for k, v in (("valid_from", action.valid_from), ("valid_to", action.valid_to)) if v is not None}
        current = {"valid_from": relationship.valid_from, "valid_to": relationship.valid_to}
        for key, value in attributes.items():
            if relationship.attributes.get(key) == value:
                continue
            changes[f"attributes.{key}"] = value
            current[f"attributes.{key}"] = relationship.attributes.get(key)
        self.emit_updates(action, "Relationship", relationship.id, changes, current)

    # lifecycle -----------------------------------------------------------

    def _lifecycle_policy(self, action, target_type):
        if target_type in ("ObjectType", "RelationshipType", "AttributeDefinition"):
            self.check_schema_policy(action)
        self.check_provenance(action)

    def do_set_active(self, action):
        target = self.resolve_lifecycle(action.target, action.action_id)
        if target is None:
            return
        target_type, target_id, currently_active = target
        self._lifecycle_policy(action, target_type)
        if currently_active == action.active:
            self.fail(
                "empty_update",
                f"This {target_type} is already {'active' if action.active else 'retired'}; omit this action.",
                action_id=action.action_id,
            )
            return
        self.emit(action.action_id, self.update_spec(target_type, target_id, "is_active", currently_active, action.active))
        self.touch(target_type, target_id, action.action_id, "reactivated" if action.active else "retired")

    def do_delete(self, action):
        target = self.resolve_lifecycle(action.target, action.action_id)
        if target is None:
            return
        target_type, target_id, _ = target
        self._lifecycle_policy(action, target_type)
        self.emit(
            action.action_id,
            {
                "operation": ProposalChange.Operation.DELETE,
                "target_type": target_type,
                "target_id": uuid.UUID(str(target_id)),
                "parent_type": "",
                "parent_id": None,
                "before": None,
                "after": None,
            },
        )
        self.touch(target_type, target_id, action.action_id, "deleted")
