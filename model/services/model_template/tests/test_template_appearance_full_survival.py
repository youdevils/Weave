"""
Decisive diagnostic for the regression report: after instantiating the
"delivery_project" (Harbour Home Retail) template -- which styles all 15
Object Types and 10 of 26 Relationship Types -- an unrelated second proposal
(a plain ObjectType rename) is reported to cause *some* types to visually
lose their icon and fall back to their base shape, while background/colour
survives.

Unlike the spot-check tests in model/services/proposal/tests/test_
appearance_isolation.py (which only check one or two fields on one or two
types), this dumps and diffs the *complete* stored appearance document,
field by field, for every styled type -- both immediately after template
instantiation (to rule out the corruption already existing before the
second proposal even runs) and again after the second proposal completes.
It also compares the *compiled* (rendered) styles from
compile_ontology_graph, to tell a storage-layer bug apart from a read/
compile-layer one.

Uses TransactionTestCase (not TestCase) so transaction.on_commit callbacks
actually fire, matching production timing.
"""

from django.test import TransactionTestCase, override_settings

from account.models import CustomUser
from model.model_templates.delivery_project import DELIVERY_PROJECT_TEMPLATE
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.services.model_template.loader import instantiate_template_via_proposal
from model.services.ontology_graph.compiler import compile_ontology_graph
from model.services.proposal import submission
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace

OBJECT_STYLE_FIELDS = ("shape", "icon", "background")
RELATIONSHIP_STYLE_FIELDS = ("colour",)


def _drain(model_id):
    while True:
        proposal = submission.claim_next(model_id)
        if proposal is None:
            return
        submission.process(proposal.id)


def _node_styles(model):
    """{object_type_key: {"shape":..., "icon":..., "background":...}} from the compiled graph."""
    payload = compile_ontology_graph(model)
    by_key = {n.data["key"]: n for n in payload.nodes}
    return {
        key: {
            "shape": node.style.shape,
            "image": node.style.image,
            "background": node.style.background,
        }
        for key, node in by_key.items()
    }


def _edge_colours(model):
    payload = compile_ontology_graph(model)
    return {edge.label: edge.style.colour for edge in payload.edges}


@override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
class TemplateAppearanceFullSurvivalTests(TransactionTestCase):
    """
    CELERY_TASK_ALWAYS_EAGER so the transaction.on_commit-deferred .delay()
    calls (which only actually fire once TransactionTestCase's real commit
    happens -- unlike plain TestCase, which suppresses them) run in-process
    instead of requiring a real broker, while still exercising the genuine
    post-commit dispatch chain production goes through.
    """

    def setUp(self):
        self.workspace = Workspace.objects.create(name="W")
        self.user = CustomUser.objects.create_user(email="u@example.com", password="pw")

    def test_full_document_and_compiled_styles_before_and_after_unrelated_proposal(self):
        model = Model.objects.create(workspace=self.workspace, name="M", revision=1)
        instantiate_template_via_proposal(model, "delivery_project", self.user)

        template_appearance = DELIVERY_PROJECT_TEMPLATE["appearance"]
        object_types = {ot.key: ot for ot in ObjectType.objects.filter(model=model)}

        # -----------------------------------------------------------
        # Step 2: dump the full raw document immediately after
        # instantiation and check it matches the template exactly.
        # -----------------------------------------------------------
        before_document = Model.objects.get(pk=model.pk).appearance

        self.assertEqual(
            len(before_document["object_types"]),
            15,
            f"expected 15 styled object types right after instantiation, "
            f"got {len(before_document['object_types'])}: "
            f"{sorted(before_document['object_types'])}",
        )
        self.assertEqual(
            len(before_document["relationship_types"]),
            10,
            f"expected 10 styled relationship types right after instantiation, "
            f"got {len(before_document['relationship_types'])}: "
            f"{sorted(before_document['relationship_types'])}",
        )

        pre_existing_mismatches = []
        for key, expected_style in template_appearance["object_types"].items():
            type_id = str(object_types[key].id)
            stored = before_document["object_types"].get(type_id)
            if stored is None:
                pre_existing_mismatches.append(f"{key} ({type_id}): entire entry MISSING")
                continue
            for field in OBJECT_STYLE_FIELDS:
                if stored.get(field) != expected_style[field]:
                    pre_existing_mismatches.append(
                        f"{key} ({type_id}).{field}: expected {expected_style[field]!r}, "
                        f"stored {stored.get(field)!r} -- BEFORE any second proposal"
                    )

        self.assertEqual(
            pre_existing_mismatches,
            [],
            "Appearance document already wrong immediately after template "
            "instantiation (before any second proposal):\n"
            + "\n".join(pre_existing_mismatches),
        )

        # -----------------------------------------------------------
        # Step 3: snapshot compiled (rendered) styles before.
        # -----------------------------------------------------------
        before_compiled_nodes = _node_styles(model)
        before_compiled_edges = _edge_colours(model)

        # -----------------------------------------------------------
        # Step 4-5: an unrelated proposal -- rename an ObjectType NOT
        # among the ones reported as affected (application, deliverable,
        # store_cluster, decision) -- exactly as object_type_editor.py
        # records the change.
        # -----------------------------------------------------------
        renamed_type = object_types["team"]
        proposal = ProposalService.get_or_create_working(model, self.user)
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="ObjectType",
            target_id=renamed_type.id,
            parent_type="Model",
            parent_id=model.id,
            field="name",
            before={"field": "name", "value": renamed_type.name},
            after={"field": "name", "value": "Delivery Team"},
        )
        ProposalService.submit(proposal)
        _drain(model.id)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)

        # -----------------------------------------------------------
        # Step 6: dump the full raw document and compiled styles after.
        # -----------------------------------------------------------
        after_document = Model.objects.get(pk=model.pk).appearance
        after_compiled_nodes = _node_styles(model)
        after_compiled_edges = _edge_colours(model)

        # -----------------------------------------------------------
        # Step 7: diff, per type, per field -- both layers.
        # -----------------------------------------------------------
        storage_diffs = []
        for key, expected_style in template_appearance["object_types"].items():
            type_id = str(object_types[key].id)
            before_stored = before_document["object_types"].get(type_id, {})
            after_stored = after_document["object_types"].get(type_id)
            if after_stored is None:
                storage_diffs.append(f"STORAGE {key} ({type_id}): entire entry now MISSING")
                continue
            for field in OBJECT_STYLE_FIELDS:
                if before_stored.get(field) != after_stored.get(field):
                    storage_diffs.append(
                        f"STORAGE {key} ({type_id}).{field}: was {before_stored.get(field)!r}, "
                        f"now {after_stored.get(field)!r}"
                    )

        from model.models.relationship_type import RelationshipType

        relationship_types = {rt.key: rt for rt in RelationshipType.objects.filter(model=model)}
        for key, expected_style in template_appearance["relationship_types"].items():
            type_id = str(relationship_types[key].id)
            before_stored = before_document["relationship_types"].get(type_id, {})
            after_stored = after_document["relationship_types"].get(type_id)
            if after_stored is None:
                storage_diffs.append(f"STORAGE {key} ({type_id}): entire entry now MISSING")
                continue
            for field in RELATIONSHIP_STYLE_FIELDS:
                if before_stored.get(field) != after_stored.get(field):
                    storage_diffs.append(
                        f"STORAGE {key} ({type_id}).{field}: was {before_stored.get(field)!r}, "
                        f"now {after_stored.get(field)!r}"
                    )

        compiled_diffs = []
        for key in before_compiled_nodes:
            before_style = before_compiled_nodes[key]
            after_style = after_compiled_nodes.get(key)
            if after_style is None:
                compiled_diffs.append(f"COMPILED node {key}: missing after")
                continue
            for field in ("shape", "image", "background"):
                if before_style[field] != after_style[field]:
                    compiled_diffs.append(
                        f"COMPILED node {key}.{field}: was {before_style[field]!r}, "
                        f"now {after_style[field]!r}"
                    )

        for label in before_compiled_edges:
            if before_compiled_edges[label] != after_compiled_edges.get(label):
                compiled_diffs.append(
                    f"COMPILED edge {label}.colour: was {before_compiled_edges[label]!r}, "
                    f"now {after_compiled_edges.get(label)!r}"
                )

        report = (
            "\n--- STORAGE (raw Model.appearance) diffs ---\n"
            + ("\n".join(storage_diffs) if storage_diffs else "(none -- storage layer unaffected)")
            + "\n--- COMPILED (compile_ontology_graph) diffs ---\n"
            + ("\n".join(compiled_diffs) if compiled_diffs else "(none -- compiled layer unaffected)")
        )

        self.assertEqual(storage_diffs, [], report)
        self.assertEqual(compiled_diffs, [], report)
