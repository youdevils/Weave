"""Shared fixtures for ai app tests."""

from django.test import TestCase

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from workspace.models import Workspace

from ai.services.operations import OperationDefinition
from ai.services.change_plan import ChangePlan
from ai.services.provider import AIProvider, ProviderResult


def fake_operation(
    operation_id="test_op",
    can_produce_proposal=True,
) -> OperationDefinition:
    return OperationDefinition(
        operation_id=operation_id,
        name="Test Operation",
        description="A synthetic operation definition used only in tests.",
        evidence="optional",
        can_produce_proposal=can_produce_proposal,
        required_context_categories=frozenset(),
        input_schema=ChangePlan,
        output_schema=ChangePlan,
    )


class ScriptedProvider(AIProvider):
    """A fake AIProvider that returns a pre-scripted sequence of structured
    results, one per generate_structured call -- used to drive the
    orchestrator's refinement loop deterministically in tests, without any
    real OpenAI calls."""

    def __init__(self, structured_results, explanation="Explained."):
        self._results = list(structured_results)
        self._index = 0
        self.explanation = explanation
        self.explain_called = False
        self.generate_calls = 0
        # Every call's system_prompt/user_payload, in order -- lets tests
        # assert on exactly what the orchestrator sent the provider each
        # refinement cycle (e.g. the empty-model system prompt sentence).
        self.system_prompts: list[str] = []
        self.user_payloads: list[dict] = []

    def generate_structured(self, *, system_prompt, user_payload, response_schema, config):
        self.generate_calls += 1
        self.system_prompts.append(system_prompt)
        self.user_payloads.append(user_payload)
        if self._index >= len(self._results):
            raise AssertionError("ScriptedProvider ran out of scripted results")
        result = self._results[self._index]
        self._index += 1
        return ProviderResult(
            parsed=result, raw_text="", usage={"total_tokens": 1}, provider="test", provider_model=config.model
        )

    def explain(self, *, context, issues, config):
        self.explain_called = True
        return self.explanation


class RaisingProvider(AIProvider):
    """A fake AIProvider whose first call always raises the given error."""

    def __init__(self, error):
        self.error = error

    def generate_structured(self, **kwargs):
        raise self.error

    def explain(self, **kwargs):
        return ""


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

    def make_object_type(self, model, key="widget", name=None):
        return ObjectType.objects.create(model=model, key=key, name=name or key.title())

    def make_relationship_type(self, model, key="depends_on", name=None):
        return RelationshipType.objects.create(model=model, key=key, name=name or key.title())

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
        return AttributeDefinition.objects.create(
            object_type=object_type,
            relationship_type=relationship_type,
            key=key,
            name=kwargs.pop("name", key.title()),
            data_type=data_type,
            **kwargs,
        )
