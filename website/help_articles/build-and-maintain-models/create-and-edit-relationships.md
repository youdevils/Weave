---
title: "Create and edit relationships"
slug: "create-and-edit-relationships"
summary: "Connect model objects with relationships that express meaningful links between them."
category: "build-and-maintain-models"
nav_order: 2
status: published
keywords:
  - relationships
  - connections
  - create relationships
  - edit relationships
related:
  - relationship-types-and-relationships
  - define-and-configure-relationship-types
  - create-and-edit-objects
updated: "2026-10-10"
---

# Create and edit relationships

Relationships describe how objects in a model connect. They turn a list of individual items into a connected picture of the subject you are modelling.

A relationship uses a **relationship type**, which defines the kind of connection and the object types it can connect. For the distinction between a relationship definition and an individual connection, see [Relationship types and relationships](/help/model-fundamentals/relationship-types-and-relationships/).

## Before you create a relationship

Make sure both endpoint objects already exist and that you know what the connection means. Choose a relationship type that expresses that meaning and allows the selected objects to be connected. If no suitable type exists, see [Define and configure relationship types](/help/build-and-maintain-models/define-and-configure-relationship-types/).

Pay attention to direction. A relationship from A to B may mean something different from a relationship from B to A. Choose the source and target according to the meaning defined by the relationship type, not simply according to where the objects appear on screen.

## Create a relationship

1. Open the model and go to its relationship editing area.
2. Choose the relationship type that describes the connection you need.
3. Select the source object and target object for the relationship.
4. Check that the direction and meaning of the connection are correct.
5. Complete any relationship attributes available for that type.
6. Save the relationship using the editor's controls.
7. Inspect the connection in the graph or Model Explorer to confirm that it joins the intended objects.

The available relationship types and valid endpoints depend on the model's configured relationship rules. If a connection is not offered or is rejected, check the type's allowed endpoints and direction rather than assuming any two objects can be connected.

## Edit or remove a relationship

Locate the connection in the model's editing interface and inspect its type, endpoints and any attributes. If the meaning of the connection has changed, update it in a way that still matches the relationship type's rules.

When changing an endpoint, verify that the new object is valid for that relationship type. When changing an attribute, use values permitted by the configured field. After saving, inspect the graph and the relevant objects to make sure the connection still communicates what you intend.

If the connection no longer represents a real or useful relationship, remove it using the available editing control. Before doing so, consider whether another relationship should replace it or whether the connection is needed to explain an important dependency.

## Good relationship practice

- **Connect for a reason.** Every relationship should communicate a meaningful fact about the subject.
- **Choose the right relationship type.** Avoid using a vague connection when the model already defines a more precise one.
- **Respect direction.** Confirm what the source-to-target direction means.
- **Avoid duplicate connections.** Before adding one, check whether the same relationship already exists.
- **Check the surrounding context.** A relationship may make sense locally but be misleading when viewed alongside related objects and connections.

## Next steps

If the relationship you need cannot be created, review [Define and configure relationship types](/help/build-and-maintain-models/define-and-configure-relationship-types/) and review the type's configured source and target object types.
