# Help & documentation articles

This directory is the live, published article corpus for `/help/`. It is
intentionally empty right now — the framework ships before the article
library does. Loader behaviour is proven against the fixtures under
`website/tests/fixtures/help_articles/`, not against this directory.

## Adding an article

1. Pick one of the six fixed categories (see `website/help_categories.py`)
   and create `website/help_articles/<category-slug>/<article-slug>.md`.
2. Add YAML frontmatter, then the Markdown body:

   ```markdown
   ---
   title: "Your article title"
   slug: your-article-slug          # must match the filename
   summary: "One or two sentences shown on cards and in search results."
   category: category-slug          # must match the parent directory
   nav_order: 1                     # position within the category; unique per category
   status: published                # "draft" articles never appear publicly
   keywords: [optional, search, terms]
   related: [another-article-slug]  # optional; article slugs are global, not category-qualified
   updated: "2026-01-01"             # optional, quoted so YAML keeps it a string
   ---

   Article body in Markdown. `## Headings` (levels 2-3) populate the
   right-hand table of contents automatically. Tables, fenced code blocks,
   and `!!! note "Title"` / `!!! warning "Title"` callouts are all
   supported.

   In-body links to other articles must be hardcoded absolute paths
   (`/help/<category-slug>/<article-slug>/`), since article bodies are
   rendered by Markdown only, not Django templates.
   ```

3. That's it — no routing or template changes are needed. The landing page,
   category page, sidebar, search and sitemap all pick up the new article
   automatically on the next request (or process restart in production,
   since articles are cached in-process and invalidated by file mtime).

Article slugs must be globally unique across every category, not just
within their own category — `website/help_content.py` validates this (and
every other frontmatter rule above) at load time and raises a clear error
for malformed content.
