"""Shared fixtures for ai app tests."""

from django.test import TestCase, override_settings

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from workspace.models import Workspace

from ai.services.artifacts import Clarification, Provenance
from ai.services.change_set import ChangeSet, PlanResult
from ai.services.evidence_graph import (
    EvidenceAssertion,
    EvidenceEntity,
    EvidenceFact,
    EvidenceGraph,
    Qualifiers,
    Supersedes,
)
from ai.services.intent_frame import FrameAnchor, FrameTarget, IntentFrame
from ai.services.provider import AIProvider, ProviderResult
from ai.services.reconcile.responses import (
    AdjudicationAnswer,
    AdjudicationResult,
    ExtractionResult,
    Objection,
    ProbeResult,
    ProbeVerdict,
    SegmentDismissal,
    VerificationResult,
)


class ScriptedProvider(AIProvider):
    """
    A fake AIProvider returning a pre-scripted sequence of structured results,
    one per generate_structured call, in order -- used to drive a staged
    workflow deterministically without any real provider calls. Every call's
    (stage, response schema, system prompt, payload) is recorded so tests can
    assert on exactly what each stage was sent.

    A scripted result whose type doesn't match the response schema the stage
    asked for fails loudly, so a mis-ordered script can't pass by accident.
    """

    def __init__(self, structured_results, explanation="Explained.", tokens_per_call=1):
        self._results = list(structured_results)
        self._index = 0
        self.explanation = explanation
        self.tokens_per_call = tokens_per_call
        self.explain_called = False
        self.explain_calls = 0
        self.generate_calls = 0
        self.system_prompts: list[str] = []
        self.user_payloads: list[dict] = []
        self.schemas: list[type] = []

    @property
    def stages(self) -> list[str]:
        return [payload.get("stage") for payload in self.user_payloads]

    def payloads_for(self, stage) -> list[dict]:
        return [payload for payload in self.user_payloads if payload.get("stage") == stage]

    def generate_structured(self, *, system_prompt, user_payload, response_schema, config):
        self.generate_calls += 1
        self.system_prompts.append(system_prompt)
        self.user_payloads.append(user_payload)
        self.schemas.append(response_schema)
        if self._index >= len(self._results):
            raise AssertionError("ScriptedProvider ran out of scripted results")
        result = self._results[self._index]
        self._index += 1
        if callable(result) and not isinstance(result, type) and not hasattr(result, "model_dump"):
            # A responder that builds its answer from what the stage sent
            # (e.g. verdicts for requirement ids only known at run time).
            result = result(user_payload)
        if not isinstance(result, response_schema):
            raise AssertionError(
                f"Scripted result #{self._index} is a {type(result).__name__}, but the "
                f"{user_payload.get('stage')} stage asked for {response_schema.__name__}"
            )
        return ProviderResult(
            parsed=result,
            raw_text="",
            usage={"total_tokens": self.tokens_per_call},
            provider="test",
            provider_model=config.model,
        )

    def explain(self, *, context, issues, config):
        self.explain_called = True
        self.explain_calls += 1
        return ProviderResult(
            parsed=None, raw_text=self.explanation, usage={"total_tokens": self.tokens_per_call}, provider="test"
        )


class RaisingProvider(AIProvider):
    """A fake AIProvider whose first call always raises the given error."""

    def __init__(self, error):
        self.error = error

    def generate_structured(self, **kwargs):
        raise self.error

    def explain(self, **kwargs):
        return ProviderResult(parsed=None, raw_text="")


# -- artifact builders ---------------------------------------------------------


def prov(excerpt, source_id="S1", segment_id=None):
    return [Provenance(source_id=source_id, excerpt=excerpt, segment_id=segment_id)]


def provs(*spans):
    """Several cited spans: (excerpt, source_id) or (excerpt, source_id, segment_id)."""

    return [Provenance(source_id=s[1], excerpt=s[0], segment_id=s[2] if len(s) > 2 else None) for s in spans]


def entity(eid, name, type_label, *, hint=None, excerpt=None, source_id="S1", specificity="specific", polarity="present", aliases=()):
    return EvidenceEntity(
        eid=eid, name=name, type_label=type_label, type_hint=hint, specificity=specificity, polarity=polarity,
        aliases=list(aliases), provenance=prov(excerpt or name, source_id),
    )


def assertion(aid, subject, predicate, obj, *, hint=None, orientation="as_stated", excerpt=None, source_id="S1", polarity="present",
              modality="stated", support="explicit", spans=None, **qualifiers):
    return EvidenceAssertion(
        aid=aid, subject_eid=subject, predicate=predicate, object_eid=obj, relationship_type_hint=hint,
        hint_orientation=orientation, polarity=polarity, modality=modality, qualifiers=Qualifiers(**qualifiers),
        support=support, provenance=provs(*spans) if spans else prov(excerpt, source_id),
    )


def fact(fid, subject, label, value, *, excerpt=None, source_id="S1", modality="stated", unit=None, supersedes=None, **qualifiers):
    return EvidenceFact(
        fid=fid, subject_id=subject, label=label, value=value, unit=unit, modality=modality,
        qualifiers=Qualifiers(**qualifiers), provenance=prov(excerpt or value, source_id),
        supersedes=Supersedes(**supersedes) if supersedes else None,
    )


def target(target_id, type_label, excerpt, *, verb="add", hint=None):
    return FrameTarget(target_id=target_id, type_label=type_label, type_hint=hint, verb=verb, excerpt=excerpt)


def anchor(anchor_id, name, excerpt, *, hint=None):
    return FrameAnchor(anchor_id=anchor_id, name=name, type_hint=hint, excerpt=excerpt)


def frame(targets=(), anchors=(), *, include_related=False, include_related_excerpt=None, restated="Reconcile the evidence."):
    return IntentFrame(
        restated_intent=restated, targets=list(targets), anchors=list(anchors), include_related=include_related,
        include_related_excerpt=include_related_excerpt,
    )


def graph(*items):
    return EvidenceGraph(
        entities=[i for i in items if isinstance(i, EvidenceEntity)],
        assertions=[i for i in items if isinstance(i, EvidenceAssertion)],
        facts=[i for i in items if isinstance(i, EvidenceFact)],
    )


def extraction(intent_frame=None, *items, dismissed=()):
    return ExtractionResult(
        intent_frame=intent_frame or frame(), evidence=graph(*items),
        dismissed_segments=[SegmentDismissal(segment_id=s, reason=r) for s, r in dismissed],
    )


def extraction_clarification(question="Which one?"):
    return ExtractionResult(clarification=Clarification(needed=True, question=question))


def answers(*pairs):
    """pairs: (question_id, option_id, excerpt)."""

    return AdjudicationResult(answers=[AdjudicationAnswer(question_id=q, option_id=o, excerpt=e) for q, o, e in pairs])


def probe(*items, verdicts=()):
    return ProbeResult(claims=graph(*items), verdicts=list(verdicts))


def nothing_stated(payload):
    """A probe responder: the segments state nothing for any requirement."""

    return ProbeResult(verdicts=[ProbeVerdict(requirement_id=r["requirement_id"], status="not_stated", segments_reviewed=r["segment_ids"])
                                 for r in payload["requirements"]])


def verdict(requirement_id, status, **kwargs):
    return ProbeVerdict(requirement_id=requirement_id, status=status, **kwargs)


def approve(*notes):
    return VerificationResult(
        verdict="approved_with_findings" if notes else "approved",
        objections=[Objection(objection_id=f"V{i}", target_kind="intent", target_id="intent", kind="scope_error", severity="minor", message=m)
                    for i, m in enumerate(notes, 1)],
    )


def objection(target_kind, target_id, kind, message="Objection.", **kwargs):
    return Objection(objection_id="V1", target_kind=target_kind, target_id=target_id, kind=kind, severity="material", message=message, **kwargs)


def reject(*objections):
    return VerificationResult(verdict="correction_required", objections=list(objections))


def plan(actions=(), summary="Proposed changes."):
    return PlanResult(change_set=ChangeSet.model_validate({"summary": summary, "actions": list(actions)}))


def existing_type(key):
    return {"kind": "existing", "key": key}


def existing_object(type_key, key):
    return {"kind": "existing", "type_key": type_key, "key": key}


def new(token):
    return {"kind": "new", "token": token}


# The legacy claims-mode suite tests the claims architecture explicitly, whatever
# the default; readings-mode tests opt in with their own override.
@override_settings(AI_RECONCILE_EVIDENCE_MODE="claims")
class AIServiceTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(email="ai@example.com", password="test-password")

    def make_model(self, **kwargs):
        kwargs.setdefault("name", "Test Model")
        kwargs.setdefault("purpose", "Track widgets.")
        kwargs.setdefault("scope", "Widgets only.")
        kwargs.setdefault("exclusions", "No gadgets.")
        return Model.objects.create(workspace=self.workspace, **kwargs)

    def make_object_type(self, model, key="widget", name=None, **kwargs):
        return ObjectType.objects.create(model=model, key=key, name=name or key.replace("_", " ").title(), **kwargs)

    def make_relationship_type(self, model, key="depends_on", name=None, **kwargs):
        return RelationshipType.objects.create(model=model, key=key, name=name or key.replace("_", " ").title(), **kwargs)

    def make_rule(self, relationship_type, subject_type, object_type, **kwargs):
        kwargs.setdefault("subject_minimum", 0)
        kwargs.setdefault("subject_maximum", None)
        kwargs.setdefault("object_minimum", 0)
        kwargs.setdefault("object_maximum", None)
        return RelationshipTypeRule.objects.create(
            relationship_type=relationship_type,
            subject_type=subject_type,
            object_type=object_type,
            **kwargs,
        )

    def make_object(self, model, object_type, name="Widget 1", **kwargs):
        return Object.objects.create(model=model, object_type=object_type, name=name, **kwargs)

    def make_relationship(self, model, relationship_type, subject, obj, **kwargs):
        return Relationship.objects.create(
            model=model,
            relationship_type=relationship_type,
            subject=subject,
            object=obj,
            **kwargs,
        )

    def make_attribute_definition(self, *, object_type=None, relationship_type=None, key="owner", data_type="text", **kwargs):
        kwargs.setdefault("nullable", True)
        return AttributeDefinition.objects.create(
            object_type=object_type,
            relationship_type=relationship_type,
            key=key,
            name=kwargs.pop("name", key.replace("_", " ").title()),
            data_type=data_type,
            **kwargs,
        )
