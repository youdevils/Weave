---
title: "Create and configure object types"
slug: "create-and-configure-object-types"
summary: "Define a kind of thing in your model and decide which details its objects can record."
category: "build-and-maintain-models"
nav_order: 3
status: published
keywords:
  - object types
  - configure object types
  - attributes
  - model structure
related:
  - object-types-and-objects
  - create-and-edit-objects
  - attributes-and-allowed-values
updated: "2026-10-10"
---

# Create and configure object types

An object type defines a kind of thing that can appear in your model. For example, a project model might have types for Workstream, Deliverable and Application. Each object of a type represents a particular instance of that kind.

You generally create an object type when the model needs to represent a new kind of thing, not whenever you add another individual object. See [Object types and objects](/help/model-fundamentals/object-types-and-objects/) for more on the distinction.

## Decide what the type represents

Before creating a type, check whether an existing type already represents the concept you need. Creating near-duplicate types makes the model harder to understand and can split similar objects across different structures.

A useful type has a clear meaning and a consistent set of details. Prefer a concise singular name such as `Workstream` or `Application`, and make sure it is distinct from the names of types already in the model.

## Create and configure a type

1. Open the model's structure or type-definition editing area.
2. Open the object-type management interface and create a new object type.
3. Give the type a clear name and any required identifying information.
4. Define the attributes that objects of this type should carry.
5. Choose suitable data types for those attributes. Use controlled choices where the possible values should be consistent, such as a status field.
6. Review any other configuration the editor offers, such as how the type is identified or displayed.
7. Save the type and check that it appears in the model's available object types.

The precise configuration options depend on the controls available in your current OnyxJar version. Configure only the details the type needs; avoid adding fields simply because they might be useful one day.

## Design useful attributes

An attribute should capture a fact about an individual object. For example, an Application might have a purpose and a criticality; a Deliverable might have a status and acceptance criteria. Choose attributes based on what users need to record or understand.

Use [Attributes and allowed values](/help/model-fundamentals/attributes-and-allowed-values/) as a guide when choosing between free-form values and controlled choices. If the same information is needed on many objects of this type, defining it consistently makes the model easier to maintain.

## Maintain an object type

Review the type when the subject or the questions the model needs to answer change. Before adding, removing or changing an attribute, consider the objects that already use the type and the information they contain.

An attribute-definition change can affect how existing data is presented or validated. Check the available values and review representative objects after making a change. If you are changing the model's structure substantially, make the change deliberately and verify the result before updating many objects.

## When to create a new type

Create a separate type when the concept is meaningfully different or needs a different set of attributes. Keep objects under the same type when they are examples of the same kind of thing and share a common structure.

For everyday creation and updates, see [Create and edit objects](/help/build-and-maintain-models/create-and-edit-objects/).
