---
title: "Find and inspect model elements in Model Explorer"
slug: "find-and-inspect-model-elements-in-model-explorer"
summary: "Locate objects, narrow the graph and inspect the attributes and connections behind a model view."
category: "build-and-maintain-models"
nav_order: 6
status: published
keywords:
  - Model Explorer
  - find objects
  - inspect relationships
  - graph filters
related:
  - navigate-your-model
  - how-an-onyxjar-model-is-structured
  - create-and-edit-objects
  - create-and-edit-relationships
updated: "2026-10-10"
---

# Find and inspect model elements in Model Explorer

Model Explorer helps you find items in a model and understand how they fit into the wider structure. The graph gives you a visual overview of objects and their relationships; selecting an item lets you examine its details and connections.

The graph is a view of the model, not the model's underlying structure. For the basic distinction between the underlying model and its visual representation, see [How an OnyxJar model is structured](/help/model-fundamentals/how-an-onyxjar-model-is-structured/).

## Find an object

1. Open the model and go to **Model Explorer**.
2. Use the available search to locate an object by its name or other supported search terms.
3. Use the object-type filters to narrow the visible set when the model contains many kinds of objects.
4. Select the object you want to investigate.
5. Inspect its details and the connections shown for it.

Filter labels and controls may be collapsed until you open them. If an object is not visible, check whether a search term or active filter is excluding it before assuming it is missing from the model.

## Read an object's details

The details view provides context beyond the object's position in the graph. Review its identifying information and attributes to understand what the object represents. Pay attention to values such as status, purpose or criticality when they are relevant to your question.

Use the connections to follow how the object relates to other parts of the model. Direction matters: check which relationships lead into the object and which lead out, and read the relationship labels to understand what each connection means.

## Narrow the graph

Use the available object-type and relationship-type filters to reduce visual clutter or focus on a particular part of the model. A filtered graph can help answer a specific question, but remember that filtering changes what you see; it does not by itself change the underlying model data.

If expected objects or connections appear to be missing, clear or adjust the relevant filters and search terms. Also consider whether the model actually contains the relationship you expect.

## Explore related objects

Select a connected object to continue exploring from a different point. Following several links can reveal dependencies, groupings or gaps that are hard to notice from an isolated record.

When you find something that needs to change, use the model's editing views rather than assuming inspection in Model Explorer changes the data. See [Create and edit objects](/help/build-and-maintain-models/create-and-edit-objects/) or [Create and edit relationships](/help/build-and-maintain-models/create-and-edit-relationships/).

## Tips for investigating a model

- Start with a specific question, such as which workstream owns a change or which applications connect to a process.
- Search first, then use type filters to narrow the view.
- Inspect attributes as well as graph connections; the graph alone may not show every relevant detail.
- Check relationship labels and direction before drawing conclusions.
- Clear filters when the visible graph seems incomplete.
