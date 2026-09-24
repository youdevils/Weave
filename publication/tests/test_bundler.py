import tempfile
from pathlib import Path

from django.test import SimpleTestCase

from publication.services.portable.bundler import BundleError, bundle_modules


class BundlerFixture(SimpleTestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def write(self, name, source):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")
        return path


class InliningTests(BundlerFixture):

    def test_dependencies_come_before_their_importers(self):
        self.write("leaf.js", "export const LEAF = 1;\nexport function twice(n) { return n * 2; }\n")
        self.write("mid.js", 'import { LEAF, twice } from "./leaf.js";\nexport const MID = twice(LEAF);\n')
        entry = self.write("entry.js", 'import { MID } from "./mid.js";\nconsole.log(MID);\n')

        bundled = bundle_modules(entry)

        self.assertEqual([p.name for p in bundled.modules], ["leaf.js", "mid.js", "entry.js"])
        self.assertLess(bundled.code.index("const LEAF"), bundled.code.index("const MID"))
        self.assertLess(bundled.code.index("const MID"), bundled.code.index("console.log"))

    def test_import_and_export_syntax_is_removed(self):
        self.write("a.js", "export const A = 1;\nexport class K {}\nexport async function f() {}\n")
        entry = self.write("b.js", 'import {\n  A,\n  K,\n  f,\n} from "./a.js";\nconst x = [A, K, f];\n')

        code = bundle_modules(entry).code

        self.assertNotIn("import ", code)
        self.assertNotIn("export ", code)
        self.assertIn("const A = 1;", code)
        self.assertIn("class K {}", code)
        self.assertIn("async function f()", code)

    def test_the_result_is_a_strict_iife_so_names_cannot_leak(self):
        entry = self.write("only.js", "const secret = 1;\n")

        code = bundle_modules(entry).code

        self.assertTrue(code.startswith('(() => {\n"use strict";'))
        self.assertTrue(code.rstrip().endswith("})();"))

    def test_a_shared_dependency_is_included_once(self):
        self.write("shared.js", "export const S = 1;\n")
        self.write("left.js", 'import { S } from "./shared.js";\nexport const L = S;\n')
        self.write("right.js", 'import { S } from "./shared.js";\nexport const R = S;\n')
        entry = self.write("entry.js", 'import { L } from "./left.js";\nimport { R } from "./right.js";\nuse(L, R);\n')

        bundled = bundle_modules(entry)

        self.assertEqual(bundled.code.count("const S = 1;"), 1)

    def test_source_map_references_are_removed(self):
        entry = self.write("lib.js", "const a = 1;\n//# sourceMappingURL=lib.js.map\n")

        self.assertNotIn("sourceMappingURL", bundle_modules(entry).code)

    def test_imports_resolve_across_directories(self):
        self.write("one/a.js", "export const A = 1;\n")
        entry = self.write("two/b.js", 'import { A } from "../one/a.js";\nuse(A);\n')

        self.assertEqual([p.name for p in bundle_modules(entry).modules], ["a.js", "b.js"])


class RejectionTests(BundlerFixture):

    def assertRejected(self, entry, fragment):
        with self.assertRaises(BundleError) as caught:
            bundle_modules(entry)
        self.assertIn(fragment, str(caught.exception))

    def test_unsupported_import_forms_are_rejected(self):
        self.write("a.js", "export const A = 1;\n")
        cases = {
            "renamed": ('import { A as B } from "./a.js";\n', "renames"),
            "namespace": ('import * as ns from "./a.js";\n', "only `import"),
            "default": ('import A from "./a.js";\n', "only `import"),
            "side-effect": ('import "./a.js";\n', "only `import"),
            "bare": ('import { x } from "some-package";\n', "relative"),
            "dynamic": ("const m = import('./a.js');\n", "dynamic import"),
            "meta": ("const u = import.meta.url;\n", "import.meta"),
        }
        for name, (source, fragment) in cases.items():
            with self.subTest(name):
                self.assertRejected(self.write(f"{name}.js", source), fragment)

    def test_unsupported_export_forms_are_rejected(self):
        cases = {
            "default": "export default 1;\n",
            "list": "const a = 1;\nexport { a };\n",
            "indented": "  export const a = 1;\n",
        }
        for name, source in cases.items():
            with self.subTest(name):
                self.assertRejected(self.write(f"e_{name}.js", source), "export")

    def test_a_missing_export_is_rejected(self):
        self.write("a.js", "export const A = 1;\n")
        entry = self.write("b.js", 'import { Nope } from "./a.js";\n')

        self.assertRejected(entry, "does not export 'Nope'")

    def test_top_level_name_collisions_are_rejected(self):
        self.write("a.js", "export const shared = 1;\n")
        self.write("b.js", "const shared = 2;\nexport const B = shared;\n")
        entry = self.write("c.js", 'import { shared } from "./a.js";\nimport { B } from "./b.js";\n')

        self.assertRejected(entry, "'shared' is declared in both")

    def test_cycles_are_rejected(self):
        self.write("a.js", 'import { B } from "./b.js";\nexport const A = 1;\n')
        entry = self.write("b.js", 'import { A } from "./a.js";\nexport const B = 1;\n')

        self.assertRejected(entry, "cycle")

    def test_a_missing_module_is_reported(self):
        entry = self.write("a.js", 'import { X } from "./gone.js";\n')

        self.assertRejected(entry, "Cannot read module")


class SharedExplorerModulesTests(SimpleTestCase):
    """The real Explorer modules that ship must stay within the inliner's subset."""

    def test_the_portable_entry_bundles(self):
        from publication.services.portable.assets import SCRIPT_ENTRY, static_path

        bundled = bundle_modules(static_path(*SCRIPT_ENTRY))

        self.assertEqual(
            sorted(p.name for p in bundled.modules),
            sorted(
                [
                    "translate.js",
                    "onyxjar-viewer.js",
                    "text.js",
                    "dataset.js",
                    "query.js",
                    "projection.js",
                    "search.js",
                    "details.js",
                    "graph.js",
                    "local-source.js",
                    "explorer-state.js",
                    "explorer-icons.js",
                    "explorer-render.js",
                    "explorer-builder.js",
                    "explorer-controller.js",
                    "copy-format.js",
                    "portable-boot.js",
                ]
            ),
        )

    def test_live_only_and_editing_modules_are_not_reachable(self):
        from publication.services.portable.assets import SCRIPT_ENTRY, static_path

        names = {p.name for p in bundle_modules(static_path(*SCRIPT_ENTRY)).modules}

        for forbidden in ("explorer-boot.js", "remote-source.js", "appearance-form.js", "appearance-boot.js",
                          "model_editing.js", "proposal.js", "sidebar.js"):
            self.assertNotIn(forbidden, names)
