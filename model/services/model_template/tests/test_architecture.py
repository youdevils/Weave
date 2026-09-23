"""
Boundaries the design depends on, asserted from the source so they cannot
erode -- mirrors ingestion/tests/test_architecture.py.

  * model_template never writes canonical data directly: everything goes
    through ProposalService/submission, never a `.objects.create(...)`-style
    write against ObjectType/AttributeDefinition/RelationshipType/
    RelationshipTypeRule/Object/Relationship.
  * model_template never imports model.services.validation directly --
    validation only happens inside submission.process().
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

MODEL_TEMPLATE = Path(__file__).resolve().parent.parent

CANONICAL_MODELS = {
    "Object",
    "Relationship",
    "ObjectType",
    "RelationshipType",
    "AttributeDefinition",
    "RelationshipTypeRule",
}
WRITE_METHODS = {
    "create",
    "bulk_create",
    "update",
    "bulk_update",
    "delete",
    "save",
    "get_or_create",
    "update_or_create",
}


def imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)

    return modules


def python_files(root):
    return [path for path in root.rglob("*.py") if "tests" not in path.parts]


class ModelTemplateBoundaryTests(SimpleTestCase):

    def test_model_template_never_imports_the_validation_package(self):
        offenders = [
            str(path.relative_to(MODEL_TEMPLATE))
            for path in python_files(MODEL_TEMPLATE)
            if any(module.startswith("model.services.validation") for module in imported_modules(path))
        ]

        self.assertEqual(offenders, [])

    def test_model_template_never_writes_canonical_models_directly(self):
        """
        No `Object.objects.create(...)`-style write against a canonical
        model anywhere in model.services.model_template; every row this
        package produces goes through ProposalService/submission.
        """

        offenders = []

        for path in python_files(MODEL_TEMPLATE):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue

                if node.func.attr not in WRITE_METHODS:
                    continue

                # e.g. Object.objects.create(...) -> Attribute(Attribute(Name Object, objects), create)
                target = node.func.value

                while isinstance(target, ast.Attribute):
                    target = target.value

                if isinstance(target, ast.Name) and target.id in CANONICAL_MODELS:
                    offenders.append(f"{path.name}:{node.lineno}")

        self.assertEqual(offenders, [])
