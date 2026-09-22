# Public website (OnyxJar)

The public OnyxJar site: `/`, `/examples/`, `/privacy/`, `/terms/`, `/contact/`. "OnyxJar" is the public brand. The
Django project package is still named `weave` internally (module paths, `manage.py`, etc.) — this is not user-facing
and is out of scope for the rebrand.

Log-in and sign-up are **stubs in the existing `account` app** (`/login/`, `/signup/`, names `account:login` /
`account:signup`): real pages that never create users, authenticate, or touch the session. `settings.LOGIN_URL` points at
`account:login`, so `@login_required` sends anonymous users to `/login/`. This app only ever links to those names, so the
real flow (email verification, Resend) replaces view bodies, not links. The application itself lives under `/workspace/`.

## Design language

`static/website/css/onyxjar.css` is a reusable, namespaced system (`--ff-*` tokens, `.ff-*` components): the palette from the
brand board (Indigo `#4F46E5` primary, Teal accent used decoratively, Sky, Ink, Slate, Mist), Plus Jakarta Sans, radii,
buttons, cards, the two-state header, the facet motif. The authenticated app can adopt it page by page. The mark is defined
once as an SVG `<symbol>` in `base.html` (`_mark.html` references it); `img/onyxjar-mark.svg` is the standalone copy used as the
favicon. Raster favicons and the social image were rendered once from that artwork.

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

- **Contact form:** validates and shows a success state, then does nothing. Nothing is logged, stored or sent (asserted by tests).
- **`WEBSITE_LEGAL_ENTITY` / `WEBSITE_CONTACT_EMAIL`** (env vars): footer and legal pages.
- **Privacy and Terms** are plain-language drafts limited to facts evident from the code; get them reviewed before launch.
- Not included: sitemap, robots.txt, analytics, rate-limiting on the contact form.
