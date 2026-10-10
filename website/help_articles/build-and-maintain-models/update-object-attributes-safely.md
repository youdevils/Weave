---
title: "Update object attributes safely"
slug: "update-object-attributes-safely"
summary: "Keep object details accurate while respecting attribute definitions and allowed values."
category: "build-and-maintain-models"
nav_order: 5
status: published
keywords:
  - update attributes
  - object attributes
  - allowed values
  - data consistency
related:
  - attributes-and-allowed-values
  - create-and-edit-objects
  - create-and-configure-object-types
updated: "2026-10-10"
---

# Update object attributes safely

Attributes record details about objects: for example, a status, purpose, criticality or acceptance criteria. Keeping them current makes the model more useful, but values should remain consistent with the way each attribute is defined.

This article focuses on updating details on an existing object. For the underlying concepts, see [Attributes and allowed values](/help/model-fundamentals/attributes-and-allowed-values/).

## Update an object's details

1. Find the object in the model's editing view or locate it in [Model Explorer](/help/build-and-maintain-models/find-and-inspect-model-elements-in-model-explorer/).
2. Open the object in the editing interface.
3. Identify the attribute that needs to change and confirm what the field represents.
4. Enter an appropriate value, using the allowed choices where the attribute is controlled.
5. Save the change using the editor's controls.
6. Reopen or inspect the object to check that the updated value is present and makes sense in context.

Use the value to describe the current state of the object, not the state you hope it will reach. If a field has a defined list of choices, use the closest valid value rather than entering a new spelling or variation elsewhere.

## Respect the attribute's definition

Attributes may use different data types and may restrict which values are valid. A text field, a date-like field and a controlled status field are not interchangeable. Enter information in the form expected by the field and follow any validation feedback shown by OnyxJar.

For controlled values, consistency matters. For example, if a status field defines `Not started`, `In progress` and `Complete`, entering a similar phrase such as `Under way` may introduce ambiguity or be rejected. Use the choices provided by the model.

## When the available attribute is wrong

Sometimes the problem is not the value on one object: the type's attribute definition may not fit the information you need to record. Before changing the definition, consider how the same attribute is used by other objects of that type.

If the field is useful but the permitted values need to change, review the type's configuration and the existing object values before making a structural change. If the information describes a different concept, it may be better represented by a separate attribute than by overloading an existing one.

See [Create and configure object types](/help/build-and-maintain-models/create-and-configure-object-types/) for guidance on maintaining the underlying definition.

## Check the wider model

An attribute change can affect how readers interpret connected items. After updating an important value such as a status or criticality, inspect the object in context and check any relationships or dependencies that make the value significant.

Keep attributes focused on the object itself. Details that describe a connection between two objects may belong on the relationship rather than on either endpoint, where the model supports relationship attributes.

## Good practice

- Use consistent values for the same concept.
- Prefer defined choices when they exist.
- Avoid changing a type's definition just to accommodate one unusual value without considering other objects.
- After saving, verify the value and its context.
- If the intended value is not allowed, understand the field definition before trying to work around it.
