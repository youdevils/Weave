"""
Boundaries the design depends on, asserted from the source so they cannot erode.

  * Import never carries its own model/proposal validation: it must not import
    model.services.validation. The existing Proposal validator is the single
    source of truth for whether a change is allowed.
  * Import is independent of the view layer: it must not import model.views
    (the one view-level call, setting the active proposal, is made from
    ingestion.views itself).
  * Import never writes canonical data directly.
"""

import ast
from pathlib import Path

from django.test import SimpleTestCase

INGESTION = Path(__file__).resolve().parent.parent
SERVICES = INGESTION / "services"

CANONICAL_MODELS = {"Object", "Relationship", "ObjectType", "RelationshipType", "AttributeDefinition"}
WRITE_METHODS = {"create", "bulk_create", "update", "bulk_update", "delete", "save", "get_or_create", "update_or_create"}


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
    return [path for path in root.rglob("*.py") if "tests" not in path.parts and "migrations" not in path.parts]


class ImportBoundaryTests(SimpleTestCase):

    def test_import_never_imports_the_validation_package(self):
        offenders = [
            str(path.relative_to(INGESTION))
            for path in python_files(INGESTION)
            if any(module.startswith("model.services.validation") for module in imported_modules(path))
        ]

        self.assertEqual(offenders, [])

    def test_import_services_never_import_the_view_layer(self):
        offenders = [
            str(path.relative_to(INGESTION))
            for path in python_files(SERVICES)
            if any(module.startswith("model.views") for module in imported_modules(path))
        ]

        self.assertEqual(offenders, [])

    def test_import_services_never_write_canonical_models(self):
        """
        No `Object.objects.create(...)`-style write against a canonical model
        anywhere in the services; the only rows an import creates go through the
        Proposal services, or are its own ImportSource.
        """

        offenders = []

        for path in python_files(SERVICES):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
                    continue

                if node.func.attr not in WRITE_METHODS:
                    continue

                # e.g. Object.objects.create(...)  ->  Attribute(Attribute(Name Object, objects), create)
                target = node.func.value

                while isinstance(target, ast.Attribute):
                    target = target.value

                if isinstance(target, ast.Name) and target.id in CANONICAL_MODELS:
                    offenders.append(f"{path.name}:{node.lineno}")

        self.assertEqual(offenders, [])

    def test_the_planners_do_not_read_proposals(self):
        """Matching and change construction see canonical data only."""

        for name in ("plan.py", "object_planner.py", "relationship_planner.py", "identity.py", "planner.py"):
            modules = imported_modules(SERVICES / name)

            self.assertFalse(
                {module for module in modules if module.startswith(("model.models.proposal", "model.services.proposal"))},
                name,
            )
