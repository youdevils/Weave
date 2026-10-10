"""
The six fixed Help & Documentation categories.

Categories are few and stable, so — like ``website/examples.py`` — they are a
small hand-edited Python registry, kept separate from the article content
files (which can be numerous and change independently).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpCategory:
    slug: str
    name: str
    description: str


HELP_CATEGORIES = (
    HelpCategory(
        slug="getting-started",
        name="Getting started",
        description="Set up your first model and learn the basics of OnyxJar.",
    ),
    HelpCategory(
        slug="model-fundamentals",
        name="Model fundamentals",
        description="The building blocks of a living model: objects, connections and structure.",
    ),
    HelpCategory(
        slug="build-and-maintain-models",
        name="Build and maintain models",
        description="Create and maintain the objects, relationships, and definitions that make up your model.",
    ),
    HelpCategory(
        slug="import-and-export",
        name="Import and export",
        description="Move structured model data in and out of OnyxJar using templates and exports.",
    ),
    HelpCategory(
        slug="publish-and-share",
        name="Publish and share",
        description="Create and share read-only views of your model, including portable HTML outputs.",
    ),
    HelpCategory(
        slug="account-and-troubleshooting",
        name="Account and troubleshooting",
        description="Find your models and resolve common data or model-constraint issues.",
    ),
)


def get_category(slug):
    """A HelpCategory from the registry, or None."""

    for category in HELP_CATEGORIES:
        if category.slug == slug:
            return category
    return None
