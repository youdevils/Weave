"""
Loads Help & Documentation articles from Markdown files with YAML frontmatter
under ``website/help_articles/<category-slug>/<article-slug>.md``.

No database, and no Django cache framework is configured anywhere in this
project (Redis is wired only as the Celery broker) — parsed articles are
cached in-process instead, keyed by a signature built from every file's path
and mtime. The cache is rebuilt only when that signature changes, which at a
few dozen small files costs one stat() per file per request when warm.

Malformed content raises HelpContentError at load time (surfaced by tests),
never silently at request time.

Article bodies are rendered by python-markdown only, never the Django
template engine — ``{% url %}`` does not work inside a ``.md`` file.
In-body cross-article links must be hardcoded absolute paths, e.g.
``/help/getting-started/roles-and-permissions/``. The ``related:``
frontmatter field (used for the sidebar "Related articles" box) is
unaffected by this; it is validated against real article slugs at load time.

Article slugs must be globally unique across the whole corpus, not just
within their category. URLs are category-scoped
(``/help/<category>/<slug>/``), but ``related:`` entries reference a bare
slug with no category prefix, so without global uniqueness a reference could
become ambiguous as the library grows past one category.
"""

import datetime as dt
import html as stdlib_html
import re
from dataclasses import dataclass
from pathlib import Path

import frontmatter
import markdown

from .help_categories import HELP_CATEGORIES

CONTENT_DIR = Path(__file__).parent / "help_articles"

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class HelpContentError(Exception):
    """Raised when an article file is malformed or violates a content invariant."""


@dataclass(frozen=True)
class Heading:
    level: int  # 2 or 3 (h1 is reserved for the page title)
    id: str
    text: str


@dataclass(frozen=True)
class HelpArticle:
    slug: str
    title: str
    summary: str
    category_slug: str
    nav_order: int
    status: str  # "draft" | "published"
    keywords: tuple
    related_slugs: tuple
    updated: str | None  # "YYYY-MM-DD" or None
    html: str
    headings: tuple
    plain_text: str
    source_path: Path


_cache_signature = None
_cache_all = None
_cache_published = None


def get_all_articles(include_drafts=False):
    """
    All articles, sorted by (category registry order, nav_order, title).

    Returns the same tuple object across calls when the corpus hasn't
    changed on disk, so callers (e.g. help_search) can cheaply detect
    whether a rebuild is needed by comparing object identity.
    """

    all_articles, published = _ensure_loaded()
    return all_articles if include_drafts else published


def get_article(category_slug, slug, include_drafts=False):
    """A single HelpArticle, or None if it doesn't exist / is filtered out."""

    for article in get_all_articles(include_drafts=True):
        if article.category_slug == category_slug and article.slug == slug:
            if include_drafts or article.status == "published":
                return article
            return None
    return None


def get_articles_in_category(category_slug, include_drafts=False):
    """Articles in one category, in nav_order (already the corpus sort order)."""

    return tuple(
        article
        for article in get_all_articles(include_drafts)
        if article.category_slug == category_slug
    )


def get_prev_next(article):
    """
    (prev, next) HelpArticle|None among *published* siblings in the same
    category, ordered by nav_order. Computed over published articles only,
    even when ``article`` itself is a draft being previewed.
    """

    siblings = get_articles_in_category(article.category_slug, include_drafts=False)

    for index, sibling in enumerate(siblings):
        if sibling.slug == article.slug:
            before = siblings[index - 1] if index > 0 else None
            after = siblings[index + 1] if index + 1 < len(siblings) else None
            return before, after

    before = None
    after = None
    for sibling in siblings:
        if sibling.nav_order < article.nav_order:
            before = sibling
        elif sibling.nav_order > article.nav_order and after is None:
            after = sibling
    return before, after


def get_related(article):
    """
    Published articles resolved from article.related_slugs, in declared
    order, silently skipping any slug that is no longer published.
    """

    by_slug = {a.slug: a for a in get_all_articles(include_drafts=False)}
    return tuple(by_slug[slug] for slug in article.related_slugs if slug in by_slug)


def clear_cache():
    """Test helper: forces a full rescan on the next call."""

    global _cache_signature, _cache_all, _cache_published
    _cache_signature = None
    _cache_all = None
    _cache_published = None


def _ensure_loaded():
    global _cache_signature, _cache_all, _cache_published

    signature = _scan_signature()
    if signature != _cache_signature:
        all_articles = _parse_all(signature)
        _cache_all = all_articles
        _cache_published = tuple(a for a in all_articles if a.status == "published")
        _cache_signature = signature

    return _cache_all, _cache_published


def _scan_signature():
    """
    Scans only the known category subdirectories (not CONTENT_DIR itself),
    so non-article files living directly in CONTENT_DIR — such as its
    authoring README — are never mistaken for articles.
    """

    entries = []
    for category in HELP_CATEGORIES:
        category_dir = CONTENT_DIR / category.slug
        if category_dir.exists():
            for path in sorted(category_dir.glob("*.md")):
                entries.append((str(path), path.stat().st_mtime_ns))
    return tuple(entries)


def _parse_all(signature):
    category_slugs = {category.slug for category in HELP_CATEGORIES}

    articles_by_slug = {}
    for path_str, _mtime in signature:
        path = Path(path_str)
        article = _parse_one(path, category_slugs)
        if article.slug in articles_by_slug:
            raise HelpContentError(
                f"{path}: slug '{article.slug}' is already used by "
                f"{articles_by_slug[article.slug].source_path} — article slugs must be "
                "globally unique across the whole corpus"
            )
        articles_by_slug[article.slug] = article

    nav_order_owners = {}
    for article in articles_by_slug.values():
        key = (article.category_slug, article.nav_order)
        if key in nav_order_owners:
            raise HelpContentError(
                f"{article.source_path}: nav_order {article.nav_order} in category "
                f"'{article.category_slug}' is already used by "
                f"{nav_order_owners[key]}"
            )
        nav_order_owners[key] = article.source_path

    for article in articles_by_slug.values():
        for related_slug in article.related_slugs:
            if related_slug not in articles_by_slug:
                raise HelpContentError(
                    f"{article.source_path}: related article '{related_slug}' does not exist"
                )

    category_order = {category.slug: index for index, category in enumerate(HELP_CATEGORIES)}
    return tuple(
        sorted(
            articles_by_slug.values(),
            key=lambda a: (category_order.get(a.category_slug, len(category_order)), a.nav_order, a.title),
        )
    )


def _parse_one(path, category_slugs):
    try:
        post = frontmatter.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HelpContentError(f"{path}: could not parse frontmatter: {exc}") from exc

    metadata = post.metadata

    def require_str(field):
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip():
            raise HelpContentError(f"{path}: '{field}' is required and must be a non-empty string")
        return value

    title = require_str("title")
    slug = require_str("slug")
    summary = require_str("summary")
    category_slug = require_str("category")
    status = require_str("status")

    nav_order = metadata.get("nav_order")
    if not isinstance(nav_order, int) or isinstance(nav_order, bool):
        raise HelpContentError(f"{path}: 'nav_order' is required and must be an integer")

    if slug != path.stem:
        raise HelpContentError(f"{path}: slug '{slug}' must match the filename '{path.stem}'")

    if category_slug != path.parent.name:
        raise HelpContentError(
            f"{path}: category '{category_slug}' must match the parent directory '{path.parent.name}'"
        )

    if category_slug not in category_slugs:
        raise HelpContentError(f"{path}: unknown category '{category_slug}'")

    if status not in ("draft", "published"):
        raise HelpContentError(f"{path}: status must be 'draft' or 'published', got '{status}'")

    keywords = metadata.get("keywords", [])
    if not isinstance(keywords, list) or not all(isinstance(k, str) for k in keywords):
        raise HelpContentError(f"{path}: 'keywords' must be a list of strings")

    related = metadata.get("related", [])
    if not isinstance(related, list) or not all(isinstance(r, str) for r in related):
        raise HelpContentError(f"{path}: 'related' must be a list of strings")

    updated = metadata.get("updated")
    if isinstance(updated, dt.datetime):
        updated = updated.date().isoformat()
    elif isinstance(updated, dt.date):
        updated = updated.isoformat()
    if updated is not None and (not isinstance(updated, str) or not _DATE_RE.match(updated)):
        raise HelpContentError(f"{path}: 'updated' must be a date string 'YYYY-MM-DD'")

    rendered_html, headings = _render_markdown(post.content)
    plain_text = _strip_tags(rendered_html)

    return HelpArticle(
        slug=slug,
        title=title,
        summary=summary,
        category_slug=category_slug,
        nav_order=nav_order,
        status=status,
        keywords=tuple(keywords),
        related_slugs=tuple(related),
        updated=updated,
        html=rendered_html,
        headings=headings,
        plain_text=plain_text,
        source_path=path,
    )


def _render_markdown(text):
    md = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "admonition"],
        extension_configs={"toc": {"toc_depth": "2-3", "permalink": False}},
    )
    rendered_html = md.convert(text)
    headings = tuple(_flatten_toc(md.toc_tokens))
    return rendered_html, headings


def _flatten_toc(tokens):
    for token in tokens:
        yield Heading(level=token["level"], id=token["id"], text=token["name"])
        yield from _flatten_toc(token.get("children", []))


def _strip_tags(rendered_html):
    text = _TAG_RE.sub(" ", rendered_html)
    text = stdlib_html.unescape(text)
    return _WHITESPACE_RE.sub(" ", text).strip()
