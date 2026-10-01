from model.services.model_graph.loader import load_effective_dataset

from ai.services.change_plan import EntityRef
from ai.services.context_expansion import (
    ExpansionState,
    expand,
    initial_expansion_state,
    resolve_context_requests,
)
from ai.services.result_schema import ContextRequest
from ai.tests.support import AIServiceTestCase


class ResolveContextRequestsTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model)
        self.relationship_type = self.make_relationship_type(self.model)
        self.subject = self.make_object(self.model, self.object_type, name="Subject")
        self.target = self.make_object(self.model, self.object_type, name="Target")
        self.relationship = self.make_relationship(self.model, self.relationship_type, self.subject, self.target)
        self.dataset = load_effective_dataset(self.model, proposal=None)

    def test_resolvable_object_reference_becomes_expansion_seed(self):
        requests = [ContextRequest(reference=EntityRef(kind="existing", id=str(self.subject.id)))]

        resolution = resolve_context_requests(requests, dataset=self.dataset)

        self.assertEqual(resolution.seeds, [str(self.subject.id)])
        self.assertEqual(resolution.unresolved, [])

    def test_resolvable_relationship_reference_resolves_to_its_endpoint_object_seeds(self):
        requests = [ContextRequest(reference=EntityRef(kind="existing", id=str(self.relationship.id)))]

        resolution = resolve_context_requests(requests, dataset=self.dataset)

        self.assertEqual(set(resolution.seeds), {str(self.subject.id), str(self.target.id)})
        self.assertEqual(resolution.unresolved, [])

    def test_unresolvable_reference_becomes_unresolved_issue_not_expansion(self):
        import uuid

        requests = [ContextRequest(reference=EntityRef(kind="existing", id=str(uuid.uuid4())))]

        resolution = resolve_context_requests(requests, dataset=self.dataset)

        self.assertEqual(resolution.seeds, [])
        self.assertEqual(len(resolution.unresolved), 1)
        self.assertEqual(resolution.unresolved[0].code, "unresolvable_context_reference")

    def test_new_kind_reference_is_unresolvable(self):
        requests = [ContextRequest(reference=EntityRef(kind="new", id="tmp:1"))]

        resolution = resolve_context_requests(requests, dataset=self.dataset)

        self.assertEqual(resolution.seeds, [])
        self.assertEqual(len(resolution.unresolved), 1)


class ExpansionStateTests(AIServiceTestCase):

    def test_initial_expansion_state_has_no_seeds(self):
        self.assertEqual(initial_expansion_state().seed_object_ids, frozenset())

    def test_expand_adds_seeds_without_mutating_original(self):
        state = initial_expansion_state()

        new_state = expand(state, ["a", "b"])

        self.assertEqual(state.seed_object_ids, frozenset())
        self.assertEqual(new_state.seed_object_ids, frozenset({"a", "b"}))

    def test_expand_is_additive_across_calls(self):
        state = expand(initial_expansion_state(), ["a"])
        state = expand(state, ["b"])

        self.assertEqual(state.seed_object_ids, frozenset({"a", "b"}))
