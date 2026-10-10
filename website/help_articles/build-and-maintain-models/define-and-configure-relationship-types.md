---
title: "Define and configure relationship types"
slug: "define-and-configure-relationship-types"
summary: "Define what a connection means, which object types it can connect, and what details it may carry."
category: "build-and-maintain-models"
nav_order: 4
status: published
keywords:
  - relationship types
  - configure relationships
  - endpoint rules
  - relationship attributes
related:
  - relationship-types-and-relationships
  - create-and-edit-relationships
  - how-an-onyxjar-model-is-structured
updated: "2026-10-10"
---

# Define and configure relationship types

A relationship type defines a kind of connection that can exist between objects. For example, a model might use relationships to express that a project contains a workstream, that a workstream is responsible for a change, or that a change delivers an outcome.

The relationship type defines the meaning and permitted structure of the connection. Individual relationships apply that definition to particular objects. See [Relationship types and relationships](/help/model-fundamentals/relationship-types-and-relationships/) for the core distinction.

## Define the meaning first

Before creating a relationship type, describe the fact it should represent. Choose a name that makes the relationship easy to understand when read between two objects. A relationship name may read naturally as a phrase, such as “contains”, “depends on” or “delivers”. Use the terms that make sense for your model.

Check whether an existing relationship type already expresses the same meaning. Several overlapping types make it harder for users to choose the correct connection and can create inconsistent data.

## Configure a relationship type

1. Open the model's structure or type-definition editing area.
2. Open the relationship-type management interface and create a new type.
3. Give it a clear name and any required identifying information.
4. Define which source object types and target object types it is allowed to connect.
5. Confirm the direction of the relationship and what the source-to-target orientation means.
6. Define any attributes needed to describe an individual relationship, if the editor supports them for this type.
7. Save the definition and review it before using it to create relationships.

The model's relationship rules constrain which connections are valid. A type intended to connect a Project to a Workstream should not also be used for an unrelated connection merely because the editor makes the same type visible in both contexts.

## Think carefully about direction and endpoints

Direction is part of the relationship's meaning. If `Project contains Workstream` is the intended meaning, reversing the endpoints would communicate something different or incorrect. Make sure the source and target object types match that meaning.

If the connection you need cannot be created, check the configured endpoint rules and relationship direction. Review the configured source and target object types and the direction of the relationship. These rules determine which connections are valid.

## Add attributes only when they belong to the relationship

Some connections need details of their own. For example, a relationship might have a role or other property that describes the connection rather than either endpoint. Where relationship attributes are supported, define only the details that help explain or distinguish that connection.

If a detail describes the source object or target object itself, it usually belongs on that object's type instead. Keeping this distinction clear avoids duplicating information and helps users know where to maintain it.

## Maintain relationship types

When updating a relationship type, consider the relationships that already use it. Changes to its meaning, endpoints, direction or attributes may affect how existing connections are understood or validated. Review the configured definition and representative connections after editing it.

Once a type is ready, use it to [create and edit relationships](/help/build-and-maintain-models/create-and-edit-relationships/).
