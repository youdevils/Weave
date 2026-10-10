import re

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import resolve, reverse

PUBLIC_PAGES = {
    "website:home": "/",
    "website:examples": "/examples/",
    "website:help": "/help/",
    "website:privacy": "/privacy/",
    "website:terms": "/terms/",
    "website:contact": "/contact/",
    "account:login": "/login/",
    "account:signup": "/signup/",
}


def visible_text(html):
    """The page body's text, tags and the head removed."""

    body = html.split("<body", 1)[-1]
    body = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", body, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))


class RoutingTests(TestCase):

    def test_every_public_page_has_its_intended_url(self):
        for name, path in PUBLIC_PAGES.items():
            self.assertEqual(reverse(name), path, name)
            self.assertEqual(resolve(path).view_name, name, path)

    def test_the_application_lives_under_workspace(self):
        self.assertEqual(reverse("workspace:index"), "/workspace/")
        self.assertEqual(reverse("workspace:create_model"), "/workspace/create-model")
        self.assertEqual(resolve("/workspace/").view_name, "workspace:index")

    def test_the_root_is_the_public_site_not_the_dashboard(self):
        self.assertEqual(resolve("/").view_name, "website:home")

    def test_anonymous_users_are_sent_to_the_login_page(self):
        response = self.client.get(reverse("workspace:index"))

        self.assertRedirects(response, "/login/?next=/workspace/", fetch_redirect_response=False)

    def test_login_required_views_elsewhere_use_the_same_login_page(self):
        response = self.client.get("/model/00000000-0000-0000-0000-000000000000/")

        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/login/?next="))

    def test_the_public_site_only_accepts_safe_methods(self):
        for name in ("website:home", "website:examples", "website:help", "website:privacy", "website:terms"):
            self.assertEqual(self.client.post(reverse(name)).status_code, 405, name)
            self.assertEqual(self.client.head(reverse(name)).status_code, 200, name)


class PageTests(TestCase):

    def get(self, name, client=None):
        return (client or self.client).get(reverse(name))

    def test_every_public_page_renders(self):
        for name in PUBLIC_PAGES:
            self.assertEqual(self.get(name).status_code, 200, name)

    def test_every_page_has_exactly_one_h1(self):
        for name in PUBLIC_PAGES:
            html = self.get(name).content.decode()
            self.assertEqual(len(re.findall(r"<h1[\s>]", html)), 1, name)

    def test_no_page_shows_the_former_project_name(self):
        for name in PUBLIC_PAGES:
            text = visible_text(self.get(name).content.decode())
            self.assertNotIn("weave", text.lower(), name)

    def test_the_homepage_carries_the_brand_tagline_and_ctas(self):
        html = self.get("website:home").content.decode()

        self.assertContains(self.get("website:home"), "Build a living model of complex work.")
        self.assertContains(self.get("website:home"), "Try OnyxJar free")
        self.assertContains(self.get("website:home"), "See an example")
        self.assertIn(f'href="{reverse("account:signup")}"', html)
        self.assertIn(f'href="{reverse("website:examples")}"', html)

    def test_the_homepage_covers_the_agreed_information_structure(self):
        html = self.get("website:home").content.decode()

        for needle in (
            'id="what"',  # What is OnyxJar?
            "Understand the whole",
            "Keep the model trustworthy",
            "Explore the connections",
            "Share what you",
            'id="how"',  # Build / Govern / Understand / Publish
            ">Build</h3>",
            ">Govern</h3>",
            ">Understand</h3>",
            ">Publish</h3>",
            'id="see"',  # See it in action
            "Business analysts",
            "Build your first living model.",
            "free during beta",
        ):
            self.assertIn(needle, html, needle)

    def test_every_page_has_the_metadata_baseline(self):
        for name, path in PUBLIC_PAGES.items():
            html = self.get(name).content.decode()
            url = f"http://testserver{path}"

            self.assertIn('<html lang="en">', html, name)
            self.assertIn('<meta name="viewport" content="width=device-width, initial-scale=1">', html, name)
            self.assertRegex(html, r"<title>[^<]+</title>", name)
            self.assertRegex(html, r'<meta name="description" content="[^"]+">', name)
            self.assertIn(f'<link rel="canonical" href="{url}">', html, name)
            self.assertIn(f'<meta property="og:url" content="{url}">', html, name)
            self.assertIn('<meta property="og:site_name" content="OnyxJar">', html, name)
            self.assertIn('<meta property="og:type" content="website">', html, name)
            self.assertIn('<meta name="twitter:card" content="summary_large_image">', html, name)
            self.assertRegex(html, r'<meta property="og:image" content="http://testserver/static/website/img/og-image\.png">', name)
            self.assertIn('rel="icon"', html, name)
            self.assertIn('rel="apple-touch-icon"', html, name)

    def test_titles_and_descriptions_are_specific_to_each_page(self):
        titles = set()
        descriptions = set()

        for name in PUBLIC_PAGES:
            html = self.get(name).content.decode()
            titles.add(re.search(r"<title>([^<]+)</title>", html).group(1))
            descriptions.add(re.search(r'name="description" content="([^"]+)"', html).group(1))

        self.assertEqual(len(titles), len(PUBLIC_PAGES))
        self.assertEqual(len(descriptions), len(PUBLIC_PAGES))
        self.assertIn("OnyxJar", " ".join(titles))

    def test_the_canonical_url_ignores_the_query_string(self):
        html = self.client.get(reverse("website:examples") + "?utm_source=x").content.decode()

        self.assertIn('<link rel="canonical" href="http://testserver/examples/">', html)

    def test_the_login_and_signup_stubs_are_not_indexed(self):
        for name in ("account:login", "account:signup"):
            self.assertIn('<meta name="robots" content="noindex">', self.get(name).content.decode(), name)

        self.assertNotIn('name="robots"', self.get("website:home").content.decode())

    def test_no_page_repeats_an_element_id(self):
        """The mark is one shared <symbol>, so gradient ids must exist exactly once."""

        for name in PUBLIC_PAGES:
            html = self.get(name).content.decode()
            ids = re.findall(r'\sid="([^"]+)"', html)

            self.assertEqual(len(ids), len(set(ids)), f"{name}: {sorted(i for i in set(ids) if ids.count(i) > 1)}")

    def test_the_brand_mark_and_logo_appear_wherever_expected(self):
        html = self.get("website:home").content.decode()

        self.assertGreaterEqual(html.count("onyxjar/brand/logos/mark.svg"), 1)  # hero
        self.assertGreaterEqual(html.count("onyxjar/brand/logos/logo-horizontal.svg"), 2)  # header, footer

    def test_the_social_and_icon_assets_exist(self):
        from django.contrib.staticfiles import finders

        for path in (
            "website/img/og-image.png",
            "onyxjar/brand/icons/favicon.svg",
            "onyxjar/brand/icons/favicon-512.png",
            "onyxjar/brand/logos/logo-horizontal.svg",
            "onyxjar/brand/logos/mark.svg",
            "website/css/onyxjar.css",
            "website/js/site.js",
        ):
            self.assertIsNotNone(finders.find(path), path)


class HeaderTests(TestCase):

    def header(self, name, client=None):
        html = (client or self.client).get(reverse(name)).content.decode()
        return re.search(r"<header.*?</header>", html, re.S).group(0)

    def test_the_homepage_starts_in_the_hero_state(self):
        header = self.header("website:home")

        self.assertIn("data-ff-hero", header)
        self.assertNotIn("is-scrolled", header)

    def test_other_pages_render_the_compact_header_directly(self):
        for name in ("website:examples", "website:help", "website:privacy", "website:terms", "website:contact", "account:login"):
            header = self.header(name)

            self.assertIn("is-scrolled", header, name)
            self.assertNotIn("data-ff-hero", header, name)

    def test_the_header_offers_the_agreed_navigation_and_cta(self):
        header = self.header("website:home")

        for label in ("What is OnyxJar?", "How it works", "Examples", "Help", "Log in", "Try it free"):
            self.assertIn(label, header)

        self.assertIn(f'href="{reverse("website:home")}#what"', header)
        self.assertIn(f'href="{reverse("website:home")}#how"', header)
        self.assertIn(f'href="{reverse("website:help")}"', header)
        self.assertIn(f'href="{reverse("account:login")}"', header)
        self.assertIn(f'href="{reverse("account:signup")}"', header)

    def test_the_help_link_is_marked_current_only_on_help_pages(self):
        self.assertIn(f'href="{reverse("website:help")}" aria-current="page"', self.header("website:help"))
        self.assertNotIn('href="' + reverse("website:help") + '" aria-current="page"', self.header("website:home"))

    def test_the_mobile_menu_is_present_and_accessible(self):
        header = self.header("website:home")

        self.assertIn("data-ff-menu-toggle", header)
        self.assertIn('aria-expanded="false"', header)
        self.assertIn('aria-controls="ff-nav"', header)
        self.assertIn('id="ff-nav"', header)
        self.assertIn('aria-label="Primary"', header)

    def test_the_current_page_is_marked(self):
        self.assertIn('aria-current="page"', self.header("website:examples"))
        self.assertNotIn('aria-current="page"', self.header("website:home"))

    def test_signed_in_users_are_offered_the_app_instead_of_login_and_signup(self):
        user = get_user_model().objects.create_user(email="member@example.com", password="pw")
        client = Client()
        client.force_login(user)

        header = self.header("website:home", client)

        self.assertIn("Open OnyxJar", header)
        self.assertIn(f'href="{reverse("workspace:index")}"', header)
        self.assertNotIn("Try it free", header)
        self.assertNotIn(">Log in<", header)


class FooterTests(TestCase):

    def test_the_footer_has_the_agreed_links_and_legal_line(self):
        html = self.client.get(reverse("website:home")).content.decode()
        footer = re.search(r"<footer.*?</footer>", html, re.S).group(0)

        self.assertIn("Build a living model of complex work.", footer)

        for name in ("website:examples", "website:help", "website:privacy", "website:terms", "website:contact", "account:login", "account:signup"):
            self.assertIn(f'href="{reverse(name)}"', footer, name)

        self.assertRegex(footer, r"&copy; \d{4} OnyxJar\. All rights reserved\.")

    def test_the_legal_entity_comes_from_settings(self):
        from django.test import override_settings

        with override_settings(WEBSITE_LEGAL_ENTITY="Example Ltd"):
            html = self.client.get(reverse("website:privacy")).content.decode()

        self.assertIn("&copy;", html)
        self.assertIn("Example Ltd", html)

    def test_the_contact_email_is_only_shown_when_configured(self):
        from django.test import override_settings

        self.assertNotIn("mailto:", self.client.get(reverse("website:privacy")).content.decode())

        with override_settings(WEBSITE_CONTACT_EMAIL="hello@example.com"):
            html = self.client.get(reverse("website:privacy")).content.decode()

        self.assertIn('href="mailto:hello@example.com"', html)


class LegalPageTests(TestCase):

    def test_privacy_and_terms_render_with_headings_and_a_date(self):
        for name, heading in (("website:privacy", "Privacy"), ("website:terms", "Terms")):
            html = self.client.get(reverse(name)).content.decode()

            self.assertIn(f">{heading}</h1>", html)
            self.assertRegex(html, r"Last updated \d{1,2} \w+ \d{4}")
            self.assertGreaterEqual(html.count("<h2"), 5, name)
