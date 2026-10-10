---
title: "Create and edit objects"
slug: "create-and-edit-objects"
summary: "Add individual things to your model and keep their details accurate as the subject changes."
category: "build-and-maintain-models"
nav_order: 1
status: published
keywords:
  - objects
  - create objects
  - edit objects
  - object details
related:
  - object-types-and-objects
  - create-and-configure-object-types
  - create-and-edit-relationships
updated: "2026-10-10"
---

# Create and edit objects

Objects represent the individual things you want to describe in a model. Depending on the subject, an object might represent a project, application, team, workstream, process, deliverable or another meaningful item.

Each object belongs to an **object type**. The type defines what kind of thing it is and which attributes can be recorded about it. Before creating an object, make sure you have the right type for it.

For the distinction between a definition and an individual item, see [Object types and objects](/help/model-fundamentals/object-types-and-objects/).

## Before you begin

Decide what the object represents and which object type fits it. If the model does not yet have a suitable type, first [create and configure an object type](/help/build-and-maintain-models/create-and-configure-object-types/).

Think about the information that will help someone understand the object. Use its name to identify it clearly, and use the available attributes to capture details such as purpose, status or other information relevant to the model.

## Create an object

1. Open the model you want to maintain.
2. Go to the model editing area for objects and choose the appropriate object type.
3. Create a new object of that type.
4. Enter a clear name and any other required identifying information.
5. Complete the available attributes. For attributes with defined choices, select an allowed value rather than inventing a new label.
6. Save the change using the controls provided in the editor.
7. Check the resulting object in the model view or Model Explorer to make sure its details look right.

The exact fields available depend on the selected object type and how that type has been configured.

## Edit an existing object

Find the object in the model editing view or [locate it in Model Explorer](/help/build-and-maintain-models/find-and-inspect-model-elements-in-model-explorer/), then open its details in the editing interface.

Update the fields that have changed and save the edit. Keep the name and attributes aligned with the real thing the object represents. Where an attribute uses controlled choices, select a value that is permitted by the model.

After editing, review the object and its connections. A change to a status or description should not accidentally change the meaning of a relationship or turn the object into a different kind of thing.

## Keep objects useful

- **Use the right type.** An object should represent one individual item, not a category or a collection of unrelated items.
- **Use meaningful names.** Names should help a reader distinguish this object from other objects of the same type.
- **Record useful detail.** Prefer attributes that help answer a real question about the subject.
- **Keep values consistent.** Use the model's defined choices and conventions where available.
- **Maintain connections as well as details.** If the real-world situation changes, check whether the object's relationships also need to change.

## Next steps

Once the important objects exist, connect them with meaningful relationships. See [Create and edit relationships](/help/build-and-maintain-models/create-and-edit-relationships/).
