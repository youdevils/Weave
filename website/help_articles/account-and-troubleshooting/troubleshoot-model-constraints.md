---
title: "Troubleshoot model constraints"
slug: "troubleshoot-model-constraints"
summary: "Understand common reasons an object update or relationship may not be accepted by your model."
category: "account-and-troubleshooting"
nav_order: 3
status: published
keywords:
  - constraints
  - validation
  - relationship rules
  - allowed values
  - invalid relationship
related:
  - relationship-types-and-relationships
  - attributes-and-allowed-values
  - create-and-configure-object-types
  - define-and-configure-relationship-types
updated: "2026-10-10"
---

# Troubleshoot model constraints

OnyxJar models use definitions and rules to keep information consistent. These rules can limit which object types a relationship can connect, and attributes can define what kind of value is expected or which choices are allowed.

When an update is rejected or a relationship cannot be created, check the definition as well as the individual item.

## A relationship cannot be created

Start by checking the relationship type you selected. Relationship types define the kind of connection being made and can constrain which object types are allowed at each end.

Check the following:

- **Endpoint types:** confirm that the source and target objects have types allowed by the relationship type.
- **Direction:** confirm that the source and target are in the intended direction. Reversing them may not be valid.
- **Required relationship attributes:** if the relationship type defines attributes that must be supplied, provide valid values for them.
- **Existing definitions:** confirm that you are using the relationship type intended for this connection, rather than a similarly named alternative.

For the underlying concepts, see [Relationship types and relationships](/help/model-fundamentals/relationship-types-and-relationships/) and [Define and configure relationship types](/help/build-and-maintain-models/define-and-configure-relationship-types/).

## An attribute value is not accepted

Check the attribute definition and compare it with the value you are entering.

- If the attribute uses a defined set of choices, select an allowed value rather than entering a different phrase.
- If the attribute expects a particular kind of data, make sure the value matches that type.
- If the attribute is required, ensure that it has a value before completing the change.
- Check for accidental spaces, spelling differences, or values copied from a source that do not match the model's allowed choices.

See [Attributes and allowed values](/help/model-fundamentals/attributes-and-allowed-values/) and [Update object attributes safely](/help/build-and-maintain-models/update-object-attributes-safely/).

## An object type or relationship type does not fit the model

If the same kind of constraint occurs repeatedly, the issue may be in the model definition rather than in one object. Review the object type's attribute definitions or the relationship type's endpoint rules. Make sure the definition reflects the way you intend to use the model before making further changes to individual records.

Where the definition itself needs to change, see [Create and configure object types](/help/build-and-maintain-models/create-and-configure-object-types/) or [Define and configure relationship types](/help/build-and-maintain-models/define-and-configure-relationship-types/).

## Still blocked?

Note the action you were attempting, the object or relationship type involved, the value or endpoint combination you used, and the exact validation message shown. That information will help distinguish an incorrect value from a constraint in the model definition.
