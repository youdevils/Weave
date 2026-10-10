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
        slug="working-with-ai-and-change",
        name="Working with AI and change",
        description="Use AI assistance and manage change safely as your model evolves.",
    ),
    HelpCategory(
        slug="data-and-publishing",
        name="Data and publishing",
        description="Import data, publish your model, and share it with others.",
    ),
    HelpCategory(
        slug="practical-guides",
        name="Practical guides",
        description="Step-by-step guidance for common tasks and workflows.",
    ),
    HelpCategory(
        slug="troubleshooting-and-account",
        name="Troubleshooting and account help",
        description="Fix common problems and manage your account.",
    ),
)


def get_category(slug):
    """A HelpCategory from the registry, or None."""

    for category in HELP_CATEGORIES:
        if category.slug == slug:
            return category
    return None
