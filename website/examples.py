"""
The examples shown on the public Examples page.

Examples are **externally managed static assets**. The website does not
generate, store, build, validate or manage the published HTML files; it only
holds this list. To add or change an example:

  1. Upload the published HTML file to the web server.
  2. Add or edit one ``Example`` entry below.
  3. Put its preview image(s) in ``website/static/website/examples/``.

That is all; nothing else in the site needs to change.

``url`` should be **same-origin** (a path on this site, such as
``/published/business-process.html``, that the web server serves), because the
"Download example" link uses the HTML ``download`` attribute, which browsers
only honour for same-origin URLs. If a file is ever served from another origin,
that server must send ``Content-Disposition: attachment`` for it to download
instead of opening.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Example:
    title: str
    description: str
    category: str  # the domain, e.g. "Business transformation"
    images: tuple  # static paths under website/static/, e.g. "website/examples/x-1.png"
    url: str  # the externally managed published HTML file


EXAMPLES = (
    Example(
        title="Business process model",
        description=(
            "A model of how an organisation runs: business processes and the activities inside them, "
            "the teams that perform them, the applications they use, the capabilities those applications "
            "support, and the customers and outcomes they serve. Download it and explore every "
            "connection in your browser."
        ),
        category="Business transformation",
        images=("website/examples/business-process-1.png",),
        url="/published/business-process.html",
    ),
)
