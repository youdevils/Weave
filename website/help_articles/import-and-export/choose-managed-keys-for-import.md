---
title: "Choose managed keys for import"
slug: "choose-managed-keys-for-import"
summary: "Use OnyxJar's managed keys to identify model elements consistently in import files."
category: "import-and-export"
nav_order: 3
status: published
keywords:
  - managed key
  - object key
  - type key
  - identifiers
related:
  - prepare-data-for-import
  - download-an-object-import-template
  - download-a-relationship-import-template
  - import-relationships-from-a-template
updated: "2026-10-10"
---

# Choose managed keys for import

Import files need a dependable way to refer to the model elements they describe. OnyxJar provides managed keys for model elements; use the keys shown in OnyxJar and requested by the generated template rather than inventing database identifiers.

## A key is not a display name

A name is meant to be readable. It can change, and two things may have similar names. A managed key is used to identify a model element in structured workflows.

When a template asks for a key, copy the key associated with the relevant object or type. Do not substitute a display name simply because it appears more readable, and do not create a database UUID or other hidden identifier that the template does not request.

## Object and type keys

Keep these concepts separate:

- **Object key:** identifies an individual object in the model.
- **Object type key:** identifies the kind of object.
- **Relationship type key:** identifies the kind of connection represented by a relationship type.

Use the key that corresponds to the column in the generated template. If you are unsure which type or object a key belongs to, check it in the model before importing.

## Keys in relationship imports

A relationship import connects a source object to a target object using a particular relationship type. The source and target must be identifiable in the target model, so the references in the import file must match the managed keys expected by the template.

Do not use object names as substitutes for keys unless the generated template explicitly asks for names. Also avoid adding a separate identifier column that is not part of the template.

## Keep keys stable in your source data

When maintaining a source spreadsheet for repeat use, keep each object's key beside its data. This makes it easier to refer to the same object consistently when preparing a relationship file or making later changes.

Do not change a key casually to make a file look tidier. Before changing a key, establish what currently uses it and whether the change is supported by the workflow.

## Related guidance

- [Prepare data for import](/help/import-and-export/prepare-data-for-import/)
- [Download an object import template](/help/import-and-export/download-an-object-import-template/)
- [Download a relationship import template](/help/import-and-export/download-a-relationship-import-template/)
