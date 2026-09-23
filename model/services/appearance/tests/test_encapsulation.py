import os
import re
from pathlib import Path

from django.test import SimpleTestCase

# The structure of Model.appearance is private to the appearance service
# package. Nothing else may read or write it (or its nested keys).
PROJECT_ROOT = Path(__file__).resolve().parents[4]
ALLOWED_DIRS = (
    PROJECT_ROOT / "model" / "services" / "appearance",
    # Declarative model templates carry their own `"appearance": {...}`
    # section (template-local object-type/relationship-type keys ->
    # background/shape/icon/colour). It is a different, template-local
    # shape, never the private Model.appearance document, and is only ever
    # consumed field-by-field through AppearanceService.set_type_style()
    # (model.services.model_template.loader.apply_template_appearance) --
    # it never reads or writes the stored document directly.
    PROJECT_ROOT / "model" / "model_templates",
)
SKIPPED_PARTS = {"migrations", "tests", "jstests", "node_modules", ".venv", "staticfiles", "static"}

# `.appearance` as an attribute of a model object, or `appearance=` as a
# queryset field/kwarg. Resolved-appearance dataclass variables named
# `appearance` (e.g. `appearance.object_type(...)`) are legitimate, so match
# only the model attribute shapes.
FORBIDDEN = [
    re.compile(r"\bmodel\.appearance\b"),
    re.compile(r"\.update\(\s*appearance\s*="),
    re.compile(r"\"appearance\"\s*:"),
    re.compile(r"\bappearance__"),
    re.compile(r"\[\s*[\"']appearance[\"']\s*\]"),
]


class AppearanceEncapsulationTests(SimpleTestCase):

    def python_sources(self):
        for directory, subdirectories, files in os.walk(PROJECT_ROOT):
            # Prune in place so vendored trees are never walked.
            subdirectories[:] = [
                name for name in subdirectories if name not in SKIPPED_PARTS and not name.startswith(".")
            ]
            for name in files:
                path = Path(directory) / name
                if path.suffix != ".py" or any(allowed in path.parents for allowed in ALLOWED_DIRS):
                    continue
                yield path

    def test_no_module_outside_the_service_touches_model_appearance(self):
        offences = []
        for path in self.python_sources():
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in FORBIDDEN:
                for match in pattern.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    offences.append(f"{path.relative_to(PROJECT_ROOT)}:{line}: {match.group(0)}")

        self.assertEqual(offences, [], "Model.appearance must only be accessed via AppearanceService")

    def test_templates_do_not_read_the_stored_document(self):
        offences = []
        for path in (PROJECT_ROOT / "model" / "templates").rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if re.search(r"model\.appearance", text):
                offences.append(str(path.relative_to(PROJECT_ROOT)))

        self.assertEqual(offences, [])
