---
title: "Download an object import template"
slug: "download-an-object-import-template"
summary: "Get the template for importing objects of a specific type."
category: "import-and-export"
nav_order: 4
status: published
keywords:
  - object template
  - download template
  - import objects
related:
  - prepare-data-for-import
  - import-objects-from-a-template
  - choose-managed-keys-for-import
updated: "2026-10-10"
---

# Download an object import template

Use an object import template when you want to add object data to a model in a structured file. Each template is associated with an object type, so start by identifying the kind of object you want to import.

## Choose the object type

Open the model's import workflow and select the option for an object import template. Choose the relevant object type and use the template that OnyxJar provides for it.

The exact fields depend on the selected type and its defined attributes. A template for one type should not be treated as a universal template for every object in a model.

If you need templates for several types, obtain the appropriate template for each type. A downloadable bundle, where offered by the current UI, is a convenience for obtaining multiple type-specific files; it does not turn them into one combined import file.

## Keep the template structure intact

The importer maps data by column position. Do not reorder, insert or remove columns, and do not assume that changing a heading changes the meaning of a column. Copy your source data into the matching existing columns.

Check any key columns and preserve the managed keys required by the template. For more information, see [Choose managed keys for import](/help/import-and-export/choose-managed-keys-for-import/).

## Prepare the file

1. Confirm that you have selected the intended object type.
2. Download its current template.
3. Add one row for each intended object, using the expected columns.
4. Check required values, allowed choices and managed keys.
5. Keep the file focused on this one object type.

For Excel workbooks, use a single worksheet per import file.

## Next step

Once the file is ready, follow [Import objects from a template](/help/import-and-export/import-objects-from-a-template/). If an issue is reported, use [Understand and resolve import errors](/help/import-and-export/understand-and-resolve-import-errors/).
