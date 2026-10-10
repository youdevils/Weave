# Public website (OnyxJar)

The public OnyxJar site: `/`, `/examples/`, `/help/`, `/privacy/`, `/terms/`, `/contact/`. "OnyxJar" is the public brand.

Log-in and sign-up are **stubs in the existing `account` app** (`/login/`, `/signup/`, names `account:login` /
`account:signup`): real pages that never create users, authenticate, or touch the session. `settings.LOGIN_URL` points at
`account:login`, so `@login_required` sends anonymous users to `/login/`. This app only ever links to those names, so the
real flow (email verification, Resend) replaces view bodies, not links. The application itself lives under `/workspace/`.

## Design language

`static/website/css/onyxjar.css` is a reusable, namespaced system (`--ff-*` tokens, `.ff-*` components): the palette from the
brand board (Indigo `#1F1B43` primary, Plum `#540054` secondary, Teal/Sky decorative accents, Ink, Slate, Mist), Plus Jakarta
Sans, radii, buttons, cards, the two-state header, the facet motif. The authenticated app can adopt it page by page. The mark
and horizontal logo are the canonical brand assets at `static/onyxjar/brand/` (`_mark.html` references the standalone mark for
the hero; the header/footer reference the horizontal logo directly). The favicon is `onyxjar/brand/icons/favicon.svg` /
`favicon-512.png` from that same asset set.

`static/website/js/site.js` is the only script: the header's hero → compact scroll state and the mobile menu (ES module with pure,
tested helpers; `website/jstests/`). Every page works without it.

## Adding or changing an example

Examples are **externally managed static assets**; the site does not generate, store or serve the published HTML.

1. Upload the published HTML file to the web server (same origin as the site, so the `download` attribute forces a download;
   a different origin must send `Content-Disposition: attachment`).
2. Add or edit one `Example(...)` in `examples.py` (title, description, category, preview images, url).
3. Put the preview screenshots in `static/website/examples/`.

The shipped entry uses an illustrative placeholder image and a placeholder URL (`/published/business-process.html`); replace both.

## Stubs and things to fill in

- **Contact form:** validates and, on success, emails the submission via the existing Resend integration
  (`account.services.emails.send_email`) to `settings.WEBSITE_CONTACT_FORM_RECIPIENT` (defaults to `support@onyxjar.com`),
  with Reply-To set to the visitor's address. Nothing is stored in the database.
- **`WEBSITE_LEGAL_ENTITY` / `WEBSITE_CONTACT_EMAIL`** (env vars): footer and legal pages.
- **Privacy and Terms** are plain-language drafts limited to facts evident from the code; get them reviewed before launch.
- Not included: analytics, rate-limiting on the contact form.

## Help & documentation

`/help/` is a Markdown-with-frontmatter documentation section, structural shell shipped ahead of the
article library (the real `website/help_articles/` corpus starts empty — see its own `README.md` for
the authoring format). `help_content.py` loads and validates articles, `help_search.py` is a small
in-process search, `help_categories.py` holds the six fixed categories, and `help_views.py` /
`templates/website/help_*.html` render the landing page, category pages, article pages and search.
`sitemaps.py` feeds `/sitemap.xml`, which `/robots.txt` references; both are new as of this feature.
The planned initial article list lives in `.Documentation/help-content-inventory.md`.
