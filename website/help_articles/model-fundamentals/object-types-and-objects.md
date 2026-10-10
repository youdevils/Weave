---
title: "Object types and objects"
slug: "object-types-and-objects"
summary: "Understand the difference between defining a kind of thing and representing a specific item in your model."
category: "model-fundamentals"
nav_order: 2
status: published
keywords:
  - object types
  - objects
  - model structure
  - instances
related:
  - how-an-onyxjar-model-is-structured
  - relationship-types-and-relationships
  - attributes-and-allowed-values
updated: "2026-10-10"
---

# Object types and objects

An **object type** defines a kind of thing your model can represent. An **object** is one particular thing of that type.

This distinction lets you describe many individual items using a consistent structure. Instead of treating every item as unrelated, a model can group similar things under the same definition and record their details in a consistent way.

## The difference in practice

Imagine a model of an organisation's applications.

- **Application** is an object type: it describes the kind of thing being modelled.
- **Customer Portal** is an object: it represents one particular application.
- **Claims Platform** is another object of the same type: it represents a different application.

The object type is the definition. Each object is a distinct item represented in the model.

The same pattern works for projects, teams, business processes, services, workstreams, deliverables and other kinds of things relevant to your subject area.

## What an object type provides

An object type gives a model a way to describe a category of things consistently. Its definition can specify attributes used to record information about objects of that type.

For example, an Application object type might define attributes for purpose, status and criticality. The particular values belong to each application object, not to the type definition itself.

The attributes available depend on the model's definition. For more about them, see [Attributes and allowed values](/help/model-fundamentals/attributes-and-allowed-values/).

## What an object represents

An object represents a particular item in the subject area. Its name helps people recognise it, while its attributes provide additional information. Relationships can then connect it to other objects in the model.

For example, an application object might be connected to a team responsible for it, a business process it supports, or a change that affects it. Those connections give the object context beyond its own description.

## Choosing the right type

When adding an item, choose the object type that best describes what the item is in the context of your model. Similar names do not necessarily mean two things are the same kind of thing: a Project and a Deliverable may both be part of the same programme, but they represent different concepts.

A few principles help keep the model clear:

- **Use types consistently.** Items that represent the same kind of thing should generally use the same object type.
- **Keep each object specific.** Represent distinct things as distinct objects when they need to be understood or connected independently.
- **Avoid unnecessary duplication.** Before creating a new object, check whether the thing is already represented in the model.
- **Choose definitions that match the subject.** If an object type makes the model harder to understand, review whether it describes the right category of thing.

You do not need an object type for every possible variation. Start with the distinctions that matter to the questions your model needs to answer.

## How objects fit into the wider model

Object types define the kinds of things the model can represent. Objects record the particular things. Attributes describe them, and relationships connect them to other objects.

Together, these pieces make a model more than a list of names: they provide a shared structure for understanding how the parts of a subject area fit together.

For the bigger picture, see [How an OnyxJar model is structured](/help/model-fundamentals/how-an-onyxjar-model-is-structured/). The next related concept is [Relationship types and relationships](/help/model-fundamentals/relationship-types-and-relationships/).
