"""
A lightweight, in-process search over published Help & Documentation
articles. Thirty to fifty documents does not warrant an external search
service or indexing library — this is plain token counting with a per-field
weight, rebuilt only when ``help_content.get_all_articles()``'s returned
object changes (relying on that function's identity-stable caching, so this
module does not need to duplicate file-watching logic).
"""

import re
from dataclasses import dataclass

from . import help_content

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset(
    {
        "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "how",
        "in", "is", "it", "of", "on", "or", "that", "the", "this", "to", "was",
        "what", "when", "where", "which", "with",
    }
)
_FIELD_WEIGHTS = {
    "title": 5,
    "keywords": 4,
    "summary": 3,
    "headings": 2,
    "body": 1,
}
_EXCERPT_RADIUS = 80


@dataclass(frozen=True)
class SearchResult:
    slug: str
    category_slug: str
    title: str
    summary: str
    excerpt: str
    score: int


_cache_articles = None
_cache_index = None


def search(query, limit=20):
    """Published articles only. Empty tuple for an empty or no-match query."""

    tokens = _tokenize(query)
    if not tokens:
        return ()

    index = _ensure_index()
    scored = []
    for fields in index.values():
        article = fields["article"]
        score = sum(
            weight * fields[field_name].get(token, 0)
            for token in tokens
            for field_name, weight in _FIELD_WEIGHTS.items()
        )
        if score > 0:
            scored.append((score, article))

    scored.sort(key=lambda pair: (-pair[0], pair[1].title))

    return tuple(
        SearchResult(
            slug=article.slug,
            category_slug=article.category_slug,
            title=article.title,
            summary=article.summary,
            excerpt=_build_excerpt(article, tokens),
            score=score,
        )
        for score, article in scored[:limit]
    )


def clear_cache():
    """Test helper: forces a full re-index on the next call."""

    global _cache_articles, _cache_index
    _cache_articles = None
    _cache_index = None


def _ensure_index():
    global _cache_articles, _cache_index

    articles = help_content.get_all_articles(include_drafts=False)
    if articles is not _cache_articles:
        _cache_index = {article.slug: _index_one(article) for article in articles}
        _cache_articles = articles
    return _cache_index


def _index_one(article):
    return {
        "article": article,
        "title": _count_tokens(article.title),
        "keywords": _count_tokens(" ".join(article.keywords)),
        "summary": _count_tokens(article.summary),
        "headings": _count_tokens(" ".join(heading.text for heading in article.headings)),
        "body": _count_tokens(article.plain_text),
    }


def _count_tokens(text):
    counts = {}
    for token in _tokenize(text):
        counts[token] = counts.get(token, 0) + 1
    return counts


def _tokenize(text):
    return [token for token in _TOKEN_RE.findall(text.lower()) if token not in _STOPWORDS]


def _build_excerpt(article, tokens):
    lower_text = article.plain_text.lower()
    for token in tokens:
        position = lower_text.find(token)
        if position == -1:
            continue
        start = max(0, position - _EXCERPT_RADIUS)
        end = min(len(article.plain_text), position + len(token) + _EXCERPT_RADIUS)
        prefix = "…" if start > 0 else ""
        suffix = "…" if end < len(article.plain_text) else ""
        return f"{prefix}{article.plain_text[start:end].strip()}{suffix}"
    return article.summary
