---
title: "Import objects from a template"
slug: "import-objects-from-a-template"
summary: "Use a type-specific template to bring object data into a model."
category: "import-and-export"
nav_order: 5
status: published
keywords:
  - import objects
  - object data
  - spreadsheet import
related:
  - download-an-object-import-template
  - prepare-data-for-import
  - understand-and-resolve-import-errors
  - create-and-edit-objects
updated: "2026-10-10"
---

# Import objects from a template

An object import adds structured object data to a model using the template for the relevant object type. Prepare the file first, then use the model's import workflow to submit it.

## Before you begin

Make sure you have the template for the intended object type. Keep its columns in their original order, and check the managed keys and attribute values before you submit the file.

If you have not prepared the file yet, start with [Download an object import template](/help/import-and-export/download-an-object-import-template/) and [Prepare data for import](/help/import-and-export/prepare-data-for-import/).

## Run the import

1. Open the model's import workflow.
2. Select the object import option and the appropriate object type if prompted.
3. Choose the completed template file.
4. Review any validation feedback shown by OnyxJar.
5. Submit the import using the available action.
6. Inspect the resulting model data to confirm that the expected objects and values are present.

The wording of controls can vary as the interface evolves; use the current labels shown in your OnyxJar environment.

## Check the result

Do not assume that selecting a file means the intended result has been achieved. Confirm that the expected objects appear under the right type and that important attributes have the values from the source data.

If something is missing or unexpected, compare the source rows with the template columns and the relevant managed keys. Correct the source file before trying again.

## Common things to check

- The file uses the template for the correct object type.
- The columns remain in the expected order.
- Required values are present and permitted choices are valid.
- Key values identify the intended model elements.
- The Excel workbook contains only one worksheet.

See [Understand and resolve import errors](/help/import-and-export/understand-and-resolve-import-errors/) for a troubleshooting checklist. For small individual changes, you can also [create and edit objects](/help/build-and-maintain-models/create-and-edit-objects/) directly in the model.
