import json
import re
from datetime import datetime, timezone

from django.test import SimpleTestCase

from model.models.proposal import Proposal
from publication.services.bundle import build_bundle, compute_digest, with_publication
from publication.services.portable.assets import load_assets
from publication.services.portable.renderer import render_document
from publication.services.portable.validator import (
    DATA_BLOCK_ID,
    PortableValidationError,
    split_document,
    validate_document,
)

from .base import PublicationTestCase

PUBLISHED_AT = datetime(2026, 9, 20, 3, 4, 5, tzinfo=timezone.utc)


class DocumentFixture(PublicationTestCase):

    def setUp(self):
        super().setUp()
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        self.ops = self.make_object(self.team_type, "Ops")
        self.make_relationship(self.alice, self.ops)

    def bundle(self, raw=None):
        result = self.normalised(raw)
        bundle = build_bundle(self.model, result.published, result.config)
        return with_publication(
            bundle, {"id": "00000000-0000-0000-0000-000000000001", "sequence": 4, "publishedAt": PUBLISHED_AT.isoformat()}
        )

    def document(self, raw=None):
        return render_document(self.bundle(raw))

    def data(self, html):
        (block,) = split_document(html)["data"]
        return json.loads(block)


class SelfContainedTests(DocumentFixture):

    def test_the_generated_document_passes_the_validator(self):
        html = self.document()

        parts = validate_document(html)

        self.assertEqual(len(parts["data"]), 1)
        self.assertEqual(len(parts["code"]), 2)  # vis-network, then the app

    def test_nothing_is_loaded_by_url(self):
        html = self.document()
        shell = re.sub(r"<script\b[^>]*>.*?</script>", "<script></script>", html, flags=re.DOTALL)
        shell = re.sub(r"<style\b[^>]*>.*?</style>", "<style></style>", shell, flags=re.DOTALL)

        for pattern in (r"<link\b", r"<img\b", r"<iframe\b", r"<form\b", r"<script[^>]+src=", r"https?://", r"//cdn", r"@import"):
            with self.subTest(pattern=pattern):
                self.assertIsNone(re.search(pattern, shell, re.IGNORECASE))

    def test_css_only_ever_references_data_uris(self):
        (*_, ) = split_document(self.document())["styles"]
        css = "\n".join(split_document(self.document())["styles"])

        urls = re.findall(r"url\(\s*[\"']?([^)\"']*)", css)

        self.assertTrue(urls, "expected the vis-network stylesheet's inline images")
        self.assertTrue(all(u.startswith("data:") for u in urls))

    def test_the_content_security_policy_forbids_every_connection(self):
        html = self.document()

        (policy,) = re.findall(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html)

        for directive in ("default-src 'none'", "connect-src 'none'", "form-action 'none'", "base-uri 'none'", "object-src 'none'"):
            self.assertIn(directive, policy)
        self.assertNotIn("unsafe-eval", policy)
        self.assertNotIn("http", policy.replace("data:", ""))

    def test_scripts_are_pinned_by_hash(self):
        import base64
        import hashlib

        html = self.document()
        (policy,) = re.findall(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html)
        hashes = re.findall(r"'sha256-([^']+)'", policy)

        self.assertEqual(len(hashes), 2)
        for body in split_document(html)["code"]:
            digest = base64.b64encode(hashlib.sha256(body.encode("utf-8")).digest()).decode("ascii")
            self.assertIn(digest, hashes)

    def test_no_code_can_reach_a_server_or_edit_a_model(self):
        for script in split_document(self.document())["code"]:
            for needle in ("fetch(", "XMLHttpRequest", "sendBeacon", "WebSocket", "csrf", "/model/", "appearance-form", "proposal_"):
                with self.subTest(needle=needle):
                    self.assertNotIn(needle, script)

    def test_the_document_is_deterministic(self):
        self.assertEqual(self.document(), self.document())

    def test_the_output_is_a_string_and_nothing_is_written(self):
        from django.conf import settings

        self.assertIsInstance(self.document(), str)
        self.assertFalse(settings.MEDIA_ROOT and __import__("os").path.exists(settings.MEDIA_ROOT))


class ContentTests(DocumentFixture):

    def test_the_embedded_bundle_is_the_published_bundle(self):
        bundle = self.bundle()

        embedded = self.data(render_document(bundle))

        self.assertEqual(embedded, bundle)
        self.assertEqual(compute_digest(embedded), bundle["digest"])

    def test_the_publication_context_is_visible(self):
        html = self.document({"title": "Board pack", "description": "For the board"})

        self.assertIn("<title>Board pack</title>", html)
        self.assertIn("Revision 1", html)
        self.assertIn('<time datetime="2026-09-20T03:04:05+00:00">20 Sep 2026</time>', html)
        self.assertIn("For the board", html)

    def test_the_theme_colour_styles_the_container(self):
        html = self.document({"presentation": {"theme_colour": "#00aa00"}})

        self.assertIn("--weave-theme: #00AA00;", html)
        self.assertIn("--weave-theme-ink: #ffffff;", html)
        self.assertIn("--weave-theme-ink: #212529;", self.document({"presentation": {"theme_colour": "#ffee00"}}))

    def test_the_explorer_surfaces_are_present(self):
        html = self.document()

        for element_id in (
            "model-explorer",
            "model-explorer-graph",
            "explorer-search",
            "explorer-results",
            "explorer-type-filters",
            "explorer-filter-builder",
            "explorer-counts",
            "explorer-chips",
            "explorer-notices",
            "explorer-details",
            "explorer-error",
            DATA_BLOCK_ID,
        ):
            with self.subTest(element_id=element_id):
                self.assertIn(f'id="{element_id}"', html)

    def test_no_edit_or_proposal_surface_is_rendered(self):
        html = self.document()
        markup = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", "", html, flags=re.DOTALL)

        self.assertNotIn("Proposed change", markup)
        self.assertNotIn("model-ontology-legend-swatch-proposed", markup)
        self.assertNotIn("<form", markup)
        self.assertNotIn("csrf", markup.lower())

    def test_pending_proposals_are_absent_from_the_file(self):
        proposal = self.working_proposal()
        self.propose_object(proposal, self.person_type.id, "Proposed Pat")
        self.add_change(proposal, operation="update", target_type="Object", target_id=self.alice.id,
                        after={"field": "name", "value": "Alice Renamed"})
        Proposal.objects.filter(pk=proposal.pk).update(status=Proposal.Status.QUEUED)

        html = self.document()

        self.assertNotIn("Proposed Pat", html)
        self.assertNotIn("Alice Renamed", html)


class HostileInputTests(DocumentFixture):
    """Everything a user can type ends up in the file, so none of it may be able to break out of it."""

    PAYLOADS = (
        "</script><script>alert(1)</script>",
        "<img src=x onerror=alert(1)>",
        '"><svg onload=alert(1)>',
        "<!-- <script>",
        "  ",
        "]]></style><style>",
        "' onmouseover='alert(1)",
    )

    def test_names_descriptions_and_titles_cannot_break_out_of_the_data_block(self):
        for payload in self.PAYLOADS:
            with self.subTest(payload=payload):
                self.make_object(self.team_type, f"Team {payload}")
                html = render_document(
                    with_publication(
                        self.bundle({"title": payload, "description": payload}),
                        {"id": "x", "sequence": 1, "publishedAt": PUBLISHED_AT.isoformat()},
                    )
                )

                validate_document(html)
                parts = split_document(html)
                self.assertEqual(len(parts["code"]), 2, "an injected script block appeared")
                embedded = self.data(html)
                self.assertTrue(any(payload in o["name"] for o in embedded["dataset"]["objects"]))
                markup = re.sub(r"<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>", "", html, flags=re.DOTALL)
                self.assertNotIn("<svg onload", markup)
                self.assertNotIn("<img src=x", markup)

    def test_the_title_is_escaped_in_markup(self):
        html = self.document({"title": "<b>Bold</b> & co"})

        self.assertIn("<title>&lt;b&gt;Bold&lt;/b&gt; &amp; co</title>", html)
        self.assertNotIn("<h1><b>", html)

    def test_a_hostile_value_cannot_satisfy_the_csp_check(self):
        self.make_object(self.team_type, "http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; connect-src 'none'\"")
        html = self.document()
        without_meta = re.sub(r"<meta http-equiv=\"Content-Security-Policy\"[^>]*>", "", html)

        with self.assertRaises(PortableValidationError):
            validate_document(without_meta)


class ValidatorTests(SimpleTestCase):

    GOOD = (
        "<!DOCTYPE html><html><head>"
        "<meta http-equiv=\"Content-Security-Policy\" content=\"default-src 'none'; connect-src 'none'\">"
        "<style>a{background:url(data:image/png;base64,AAAA)}</style></head><body>"
        "<script type=\"application/json\" id=\"weave-published-data\">{\"a\": 1}</script>"
        "<script>var x = 1;</script></body></html>"
    )

    def test_a_minimal_good_document_passes(self):
        validate_document(self.GOOD)

    def bad(self, replacement, fragment):
        html = replacement
        with self.assertRaises(PortableValidationError) as caught:
            validate_document(html)
        self.assertIn(fragment, str(caught.exception))

    def test_each_kind_of_external_reference_is_rejected(self):
        cases = {
            "script src": ("</body>", '<script src="https://x/y.js"></script></body>', "loaded from a URL"),
            "link": ("</head>", '<link rel="stylesheet" href="x.css"></head>', "external resource"),
            "img": ("</body>", '<img src="x.png"></body>', "external resource"),
            "iframe": ("</body>", '<iframe src="x"></iframe></body>', "external resource"),
            "form": ("</body>", '<form action="x"></form></body>', "external resource"),
            "import": ("<style>", "<style>@import 'x.css';", "imports"),
            "css url": ("url(data:image/png;base64,AAAA)", "url(https://x/y.png)", "by URL"),
        }
        for name, (old, new, fragment) in cases.items():
            with self.subTest(name):
                self.bad(self.GOOD.replace(old, new, 1), fragment)

    def test_code_that_could_reach_a_server_is_rejected(self):
        for needle in ("fetch('/x')", "new XMLHttpRequest()", "navigator.sendBeacon('/x')", "new WebSocket('ws://x')", "csrfToken"):
            with self.subTest(needle=needle):
                self.bad(self.GOOD.replace("var x = 1;", needle), "Shipped code contains")

    def test_the_data_block_must_exist_once_and_parse(self):
        self.bad(self.GOOD.replace('{"a": 1}', "{not json"), "not valid JSON")
        self.bad(self.GOOD.replace('id="weave-published-data"', 'id="other"'), "Unexpected JSON block")
        doubled = self.GOOD.replace("</body>", '<script type="application/json" id="weave-published-data">{}</script></body>')
        self.bad(doubled, "exactly one data block")

    def test_the_csp_is_required(self):
        self.bad(self.GOOD.replace("connect-src 'none'", "connect-src *"), "Content-Security-Policy")


class AssetTests(SimpleTestCase):

    def test_the_shipped_script_contains_the_explorer_and_no_live_wiring(self):
        assets = load_assets()

        self.assertIn("createLocalSource", assets.app_script)
        self.assertIn("createExplorer", assets.app_script)
        self.assertNotIn("createRemoteSource", assets.app_script)
        self.assertNotIn("sourceMappingURL", assets.vis_script)
        self.assertNotIn("import ", assets.app_script.replace("// import", ""))
        self.assertIn("weave-icon", assets.app_script)

    def test_the_css_carries_the_explorer_and_portable_layers(self):
        css = load_assets().css

        for selector in (".model-explorer-layout", ".weave-icon", ".weave-published-header", ".vis-network"):
            self.assertIn(selector, css)
