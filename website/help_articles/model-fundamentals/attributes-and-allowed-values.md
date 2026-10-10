---
title: "Attributes and allowed values"
slug: "attributes-and-allowed-values"
summary: "Learn how attributes record useful details and how defined choices can keep model information consistent."
category: "model-fundamentals"
nav_order: 4
status: published
keywords:
  - attributes
  - allowed values
  - choices
  - object details
  - consistency
related:
  - how-an-onyxjar-model-is-structured
  - object-types-and-objects
  - relationship-types-and-relationships
updated: "2026-10-10"
---

# Attributes and allowed values

Attributes record details that help people understand the things and connections represented in a model. They add information beyond an object's name and make it possible to describe relevant characteristics such as purpose, status or criticality.

The attributes available in a model depend on its definitions. This helps keep information relevant to the kind of thing being described instead of giving every object an identical, unrestricted set of fields.

## Attributes describe model content

An object type can define the attributes used to describe objects of that type. Each object then has its own values for those attributes.

For example, an Application object type might define attributes for purpose and status. One application could have a purpose of “manage customer claims” and a status of “In service”, while another application has different values.

The definition establishes which details are available; the values describe the particular object.

## Choose attributes that answer useful questions

A useful attribute captures information that helps someone understand, compare, or work with the subject being modelled. Before adding or using an attribute, consider what people need to know.

For example:

- **Purpose** can explain why an item exists.
- **Status** can communicate its current state.
- **Criticality** can distinguish the relative importance of items, if that distinction is useful to the model.

These are examples, not a universal set of required attributes. A model should use attributes that fit its purpose and definitions. Too many fields can make information harder to maintain; too few can leave important questions unanswered.

## What allowed values do

Some attributes are configured with a defined set of allowed choices. Instead of allowing a different free-text phrase each time, the model can offer a consistent set of values for that attribute.

For example, a model might define a Status attribute with choices such as *Not started*, *In progress* and *Complete*. Another model may need a different set of choices to reflect its subject area.

Defined choices help people use the same terms consistently. They also make it easier to compare values across objects and interpret what a status means.

Use the choices provided by the model's definition. If none of the available values accurately describes the situation, do not quietly substitute a different spelling or invent a new category. The model definition may need to be reviewed by whoever maintains its structure.

Not every attribute is necessarily a choice field. Follow the field and value options available for the attribute you are working with, and avoid assuming that every attribute has the same rules.

## Attributes can describe relationships too

Attributes are often associated with objects, but a relationship type can also define attributes for the connections it represents.

This is useful when a detail belongs to the connection itself rather than to either object at its ends. For example, if a relationship represents responsibility between a team and a service, a model may define information about that responsibility on the relationship.

Only use relationship attributes when they are part of the relationship type's definition.

## Keep values meaningful and consistent

When recording attribute values:

- Use clear, specific wording that others will understand.
- Use the defined allowed choices where they are provided.
- Avoid storing the same fact in multiple places unless there is a clear reason.
- Review whether a value is still accurate as the subject changes.
- Keep the distinction between an attribute's definition and the value recorded for an individual object or relationship.

Consistent attributes make a model easier to interpret and maintain. They also complement relationships: attributes explain details about an item or connection, while relationships show how parts of the model fit together.

## How attributes fit into the model

Object types and relationship types establish the structure available for recording information. Attributes provide details within that structure, and objects and relationships hold the particular information represented in the model.

For the overview, see [How an OnyxJar model is structured](/help/model-fundamentals/how-an-onyxjar-model-is-structured/). For the definitions that provide object attributes, see [Object types and objects](/help/model-fundamentals/object-types-and-objects/); for relationship attributes, see [Relationship types and relationships](/help/model-fundamentals/relationship-types-and-relationships/).
