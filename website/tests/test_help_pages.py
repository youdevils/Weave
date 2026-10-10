import re
from pathlib import Path
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from website import help_content, help_search
from website.help_categories import HELP_CATEGORIES

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "help_articles"


def visible_text(html):
    body = html.split("<body", 1)[-1]
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


class FixtureContentTestCase(TestCase):
    """Points help_content/help_search at the test fixtures tree for the test."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(help_content, "CONTENT_DIR", FIXTURES_DIR)
        patcher.start()
        self.addCleanup(patcher.stop)
        help_content.clear_cache()
        help_search.clear_cache()
        self.addCleanup(help_content.clear_cache)
        self.addCleanup(help_search.clear_cache)


class RealCorpusLandingPageTests(TestCase):
    """The real, as-shipped corpus is empty — every category should say so."""

    def setUp(self):
        super().setUp()
        help_content.clear_cache()
        help_search.clear_cache()
        self.addCleanup(help_content.clear_cache)
        self.addCleanup(help_search.clear_cache)

    def test_every_real_category_currently_shows_the_coming_soon_state(self):
        response = self.client.get(reverse("website:help"))

        self.assertEqual(response.content.decode().count("Coming soon"), len(HELP_CATEGORIES))


class LandingPageTests(FixtureContentTestCase):

    def test_the_landing_page_lists_the_six_fixed_categories_in_order(self):
        response = self.client.get(reverse("website:help"))

        names = [category.name for category in HELP_CATEGORIES]
        html = response.content.decode()
        positions = [html.index(name) for name in names]

        self.assertEqual(positions, sorted(positions))

    def test_a_category_with_no_published_articles_shows_the_coming_soon_badge(self):
        response = self.client.get(reverse("website:help"))

        self.assertContains(response, "Coming soon")

    def test_the_landing_page_has_a_search_form(self):
        response = self.client.get(reverse("website:help"))

        self.assertContains(response, f'action="{reverse("website:help_search")}"')

    def test_only_safe_methods_are_allowed(self):
        response = self.client.post(reverse("website:help"))

        self.assertEqual(response.status_code, 405)


class CategoryPageTests(FixtureContentTestCase):

    def test_a_populated_category_lists_its_published_articles_only(self):
        response = self.client.get(reverse("website:help_category", args=["getting-started"]))

        self.assertContains(response, "What is OnyxJar?")
        self.assertContains(response, "Roles and permissions")
        self.assertNotContains(response, "Upcoming integrations")

    def test_an_empty_category_shows_the_coming_soon_empty_state(self):
        response = self.client.get(reverse("website:help_category", args=["model-fundamentals"]))

        self.assertContains(response, "coming soon")

    def test_an_unknown_category_slug_returns_404(self):
        response = self.client.get(reverse("website:help_category", args=["not-a-category"]))

        self.assertEqual(response.status_code, 404)


class ArticlePageTests(FixtureContentTestCase):

    def article_url(self, slug):
        return reverse("website:help_article", args=["getting-started", slug])

    def test_an_unknown_article_slug_returns_404(self):
        response = self.client.get(self.article_url("does-not-exist"))

        self.assertEqual(response.status_code, 404)

    def test_a_drafts_url_returns_404_even_though_it_exists_on_disk(self):
        response = self.client.get(self.article_url("upcoming-integrations-preview"))

        self.assertEqual(response.status_code, 404)

    def test_the_article_page_renders_breadcrumbs(self):
        response = self.client.get(self.article_url("roles-and-permissions"))

        self.assertContains(response, 'aria-label="Breadcrumb"')
        self.assertContains(response, "Getting started")
        self.assertContains(response, "Roles and permissions")

    def test_an_article_with_three_or_more_headings_shows_a_toc(self):
        response = self.client.get(self.article_url("what-is-onyxjar"))

        self.assertContains(response, 'class="ff-help-toc-slot"')
        self.assertContains(response, 'aria-label="On this page"')

    def test_a_short_article_does_not_show_a_toc(self):
        response = self.client.get(self.article_url("roles-and-permissions"))

        self.assertNotContains(response, 'class="ff-help-toc-slot"')

    def test_the_article_page_shows_related_articles(self):
        response = self.client.get(self.article_url("what-is-onyxjar"))

        self.assertContains(response, "Related articles")
        self.assertContains(response, "Roles and permissions")

    def test_prev_next_links_follow_nav_order_within_the_category(self):
        response = self.client.get(self.article_url("what-is-onyxjar")).content.decode()
        self.assertIn("Roles and permissions", response)
        self.assertNotIn("ff-help-prevnext-link--prev", response)

        response = self.client.get(self.article_url("roles-and-permissions")).content.decode()
        self.assertIn('ff-help-prevnext-link--prev', response)
        self.assertNotIn('ff-help-prevnext-link--next', response)

    def test_the_sidebar_and_toc_render_both_a_desktop_nav_and_a_mobile_disclosure(self):
        """
        Markup/class assertions only — this confirms the responsive structure
        exists, not that it renders correctly at each viewport width, which
        is verified by hand in a real browser (see the implementation plan).
        A plain CSS override cannot reliably force a *closed* <details>'s
        content to stay visible (browsers hide it via an internal content
        box, not just an overridable `display` rule), so desktop and mobile
        each get their own element instead of sharing one <details>.
        """

        response = self.client.get(self.article_url("what-is-onyxjar")).content.decode()

        self.assertIn('class="ff-help-panel ff-help-panel--desktop" aria-label="Help categories"', response)
        self.assertIn('class="ff-help-panel ff-help-panel--desktop" aria-label="On this page"', response)
        self.assertIn('<details class="ff-help-panel ff-help-panel--mobile">', response)
        self.assertEqual(response.count("<summary>Browse help</summary>"), 1)
        self.assertEqual(response.count("<summary>On this page</summary>"), 1)


class HelpPageMetadataTests(FixtureContentTestCase):
    """The same metadata baseline test_pages.py enforces for every public page."""

    def urls(self):
        return [
            reverse("website:help"),
            reverse("website:help_category", args=["getting-started"]),
            reverse("website:help_article", args=["getting-started", "what-is-onyxjar"]),
        ]

    def test_every_help_page_has_the_metadata_baseline(self):
        for url in self.urls():
            html = self.client.get(url).content.decode()

            self.assertRegex(html, r'<html lang="en">', url)
            self.assertRegex(html, r"<title>[^<]+</title>", url)
            self.assertRegex(html, r'<meta name="description" content="[^"]+">', url)
            self.assertRegex(html, r'<link rel="canonical" href="[^"]+">', url)

    def test_help_pages_have_exactly_one_h1(self):
        for url in self.urls():
            html = self.client.get(url).content.decode()

            self.assertEqual(len(re.findall(r"<h1[ >]", html)), 1, url)

    def test_titles_and_descriptions_are_specific_to_each_help_page(self):
        titles = set()
        descriptions = set()
        for url in self.urls():
            html = self.client.get(url).content.decode()
            title = re.search(r"<title>([^<]+)</title>", html).group(1)
            description = re.search(r'<meta name="description" content="([^"]*)">', html).group(1)
            titles.add(title)
            descriptions.add(description)

        self.assertEqual(len(titles), len(self.urls()))
        self.assertEqual(len(descriptions), len(self.urls()))
