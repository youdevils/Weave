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
        title="Kauri Ridge Dairy Farm",
        description=(
            "Kauri Ridge Dairy Farm is an example OnyxJar model demonstrating how the"
            "operations of a dairy farm can be represented as a connected, living model. "
            "This example brings together the farm’s people, livestock, pasture, infrastructure,"
            "processes, and operational activities to show how these elements relate to one another"
            "and support the day-to-day running of the farm."
        ),
        category="Agriculture | Dark Theme",
        images=("website/examples/kauri_farm.png",),
        url="/published/farm_example.html",
    ),
    Example(
        title="Complex Delivery Project",
        description=(
            "A fictional example showing how OnyxJar can model a complex delivery project as a connected, "
            "governed model. It follows the Harbour Home Retail EFTPOS Replacement project, linking workstreams, "
            "changes, deliverables, tests, releases, processes, applications, teams and capabilities to show "
            "how the work fits together, what it affects, how it is progressing, and how the existing environment "
            "will transition to the target state."
        ),
        category="Complex | Business",
        images=("website/examples/complex_project.png",),
        url="/published/complex_project_example.html",
    ),
)
