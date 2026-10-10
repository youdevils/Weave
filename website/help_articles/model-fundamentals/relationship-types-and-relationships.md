---
title: "Relationship types and relationships"
slug: "relationship-types-and-relationships"
summary: "Learn how relationship types define meaningful connections and relationships record connections between particular objects."
category: "model-fundamentals"
nav_order: 3
status: published
keywords:
  - relationships
  - relationship types
  - connections
  - source
  - target
related:
  - how-an-onyxjar-model-is-structured
  - object-types-and-objects
  - attributes-and-allowed-values
updated: "2026-10-10"
---

# Relationship types and relationships

Objects represent the things in a model. **Relationships** record how those things connect. A **relationship type** defines the kind of connection being represented, while a relationship records a particular connection between objects.

This distinction makes connections explicit and consistent. It helps people understand not only which things are in the model, but also how they relate to one another.

## The difference in practice

Imagine a model containing a project and several workstreams.

- A **relationship type** defines a meaningful kind of connection, such as a project containing a workstream.
- A **relationship** records that a particular project is connected to a particular workstream in that way.

If the model includes several workstreams, each connection can be represented explicitly. The relationship type provides the shared meaning; each relationship identifies the specific objects connected.

## Relationships connect existing objects

A relationship connects objects at its two ends. These are commonly understood as the source and target of the connection. The objects provide the context; the relationship records how they are connected.

For example, a project may be connected to a workstream, and that workstream may be connected to a deliverable. Following those relationships helps explain how work is organised and how one part of the model relates to another.

A relationship is not the same as a sentence mentioning two things in a description. It is an explicit connection in the model that can be explored in the graph and inspected alongside the connected objects.

## Why relationship types matter

A relationship type gives a connection consistent meaning. Without a clear definition, a line between two objects may show that they are connected without explaining why the connection matters.

Choose a relationship type that describes the relationship you intend to represent. For example, *supports*, *owns* and *depends on* describe different ideas; they should not be used interchangeably simply because the same two objects are involved.

Direction can matter too. A relationship such as “Project contains Workstream” expresses a different meaning from “Workstream contains Project”. Pay attention to the intended meaning and direction when creating or interpreting a connection.

Use relationships when a connection helps someone understand the subject area. You do not need to connect every pair of objects. A focused model with meaningful connections is usually easier to interpret than one filled with links that add little information.

## Relationships can have their own details

The objects at either end describe the things being connected. In some models, the relationship itself can also have attributes.

For example, a model might record a detail about a responsibility or dependency represented by a connection. These attributes belong to the relationship rather than automatically belonging to either connected object. The attributes available depend on how the relationship type is defined.

See [Attributes and allowed values](/help/model-fundamentals/attributes-and-allowed-values/) for more about attributes.

## How relationships appear in the graph

The graph provides a visual way to explore objects and their connections. Selecting a relationship can help you inspect what it connects and understand its place in the wider model.

The graph is a view of the underlying model, not a substitute for its definitions. Relationship types provide meaning, and individual relationships record the actual connections represented in the data.

## Keep connections clear

Before creating a relationship, consider what it communicates:

- Does the connection describe a meaningful association between these objects?
- Is the selected relationship type the right one for that meaning?
- Is the direction of the connection correct?
- Would the connection help someone understand context, responsibility, structure or dependency?

For the overall model structure, see [How an OnyxJar model is structured](/help/model-fundamentals/how-an-onyxjar-model-is-structured/). To understand the items being connected, see [Object types and objects](/help/model-fundamentals/object-types-and-objects/).
