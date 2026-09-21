from unittest.mock import patch

from django.contrib.staticfiles import finders
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from website.examples import EXAMPLES, Example


class ExampleRegistryTests(SimpleTestCase):
    """The registry is hand-edited, so guard the shape of every entry."""

    def test_the_registry_is_not_empty_and_every_entry_is_complete(self):
        self.assertGreaterEqual(len(EXAMPLES), 1)

        for example in EXAMPLES:
            self.assertIsInstance(example, Example)
            for field in ("title", "description", "category", "url"):
                self.assertTrue(getattr(example, field).strip(), f"{example.title}: {field}")
            self.assertTrue(example.images, f"{example.title}: needs at least one preview image")

    def test_every_preview_image_is_a_real_static_file(self):
        for example in EXAMPLES:
            for image in example.images:
                self.assertIsNotNone(finders.find(image), image)

    def test_titles_are_unique(self):
        titles = [example.title for example in EXAMPLES]

        self.assertEqual(len(titles), len(set(titles)))


class ExamplesPageTests(TestCase):

    url = property(lambda self: reverse("website:examples"))

    def sample(self, **overrides):
        fields = {
            "title": "Sample model",
            "description": "A sample description.",
            "category": "Sample domain",
            "images": ("website/examples/business-process-1.png",),
            "url": "/published/sample.html",
        }
        fields.update(overrides)
        return Example(**fields)

    def test_each_configured_example_is_shown_as_a_showcase_card(self):
        response = self.client.get(self.url)

        for example in EXAMPLES:
            self.assertContains(response, example.title)
            self.assertContains(response, example.category)
            self.assertContains(response, example.description)
            for image in example.images:
                self.assertContains(response, f"/static/{image}")

    def test_each_card_has_a_download_link_to_the_configured_file(self):
        response = self.client.get(self.url)

        for example in EXAMPLES:
            self.assertContains(response, f'<a class="ff-btn ff-btn--primary" href="{example.url}" download>Download example</a>', html=False)

    def test_the_link_is_a_plain_download_not_a_viewer_or_iframe(self):
        html = self.client.get(self.url).content.decode()

        self.assertNotIn("<iframe", html)
        self.assertNotIn('target="_blank"', html)

    def test_adding_an_entry_needs_only_the_registry(self):
        entries = (self.sample(), self.sample(title="Another model", url="/published/another.html"))

        with patch("website.views.EXAMPLES", entries):
            html = self.client.get(self.url).content.decode()

        self.assertIn("Sample model", html)
        self.assertIn("Another model", html)
        self.assertIn('href="/published/another.html" download', html)
        self.assertEqual(html.count("Download example"), 2)

    def test_several_images_are_all_shown(self):
        images = ("website/examples/business-process-1.png", "website/img/og-image.png")

        with patch("website.views.EXAMPLES", (self.sample(images=images),)):
            html = self.client.get(self.url).content.decode()

        self.assertIn("ff-example-images--multi", html)
        for image in images:
            self.assertIn(f"/static/{image}", html)

    def test_registry_text_is_escaped(self):
        entry = self.sample(title="<b>Bold</b>", description="<script>alert(1)</script>")

        with patch("website.views.EXAMPLES", (entry,)):
            html = self.client.get(self.url).content.decode()

        self.assertNotIn("<script>alert(1)</script>", html)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", html)
        self.assertIn("&lt;b&gt;Bold&lt;/b&gt;", html)

    def test_an_empty_registry_shows_a_friendly_message(self):
        with patch("website.views.EXAMPLES", ()):
            response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Examples are on their way")
        self.assertNotContains(response, "Download example")

    def test_the_website_does_not_serve_or_manage_the_published_files(self):
        """Examples are externally managed static assets: the site has no route for them."""

        from django.urls import Resolver404, resolve

        for example in EXAMPLES:
            with self.assertRaises(Resolver404):
                resolve(example.url)
