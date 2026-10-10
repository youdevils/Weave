---
title: "Understand and resolve import errors"
slug: "understand-and-resolve-import-errors"
summary: "Diagnose common problems with import files and correct the source data."
category: "import-and-export"
nav_order: 8
status: published
keywords:
  - import errors
  - validation
  - troubleshooting
related:
  - prepare-data-for-import
  - import-objects-from-a-template
  - import-relationships-from-a-template
updated: "2026-10-10"
---

# Understand and resolve import errors

When an import does not work as expected, start with the source file and the template it was built from. Many import problems are caused by a mismatch between the file structure, the managed keys, the values and the model's rules.

## Check the file structure first

- **Wrong template:** make sure the file was generated for the object type or relationship type you intend to import.
- **Changed column order:** the importer maps values by column position. Restore the template's original order if columns have been moved, inserted or removed.
- **Multiple worksheets:** an Excel workbook for an import must contain a single worksheet.
- **Mixed content types:** keep each file focused on one target type.

Start with [Prepare data for import](/help/import-and-export/prepare-data-for-import/) if you need to rebuild the file from a clean template.

## Check keys and references

If a row refers to an object or type, confirm that its managed key is the one recorded in OnyxJar. A display name is not a substitute for a key column. For relationship imports, check both endpoints and confirm that the referenced objects exist in the model.

See [Choose managed keys for import](/help/import-and-export/choose-managed-keys-for-import/) for the difference between object keys and type keys.

## Check attribute values

Check that required values are present and that any constrained values match the choices allowed by the model. Look for spelling differences, unexpected blank values, and values that were pasted into the wrong column.

For relationship files, check that the selected relationship type allows the object types at both endpoints. Also verify that the source and target have not been reversed.

## Correct the source and try again

1. Keep a copy of the file that produced the error.
2. Compare its columns with a fresh template for the intended type.
3. Correct the identified columns or values in a working copy.
4. Recheck the file structure and keys.
5. Submit the corrected file and inspect the resulting model data.

Avoid changing unrelated model definitions just to force an import through. First establish whether the source data matches the model you intend to maintain.

If the same problem persists, record the relevant type, the affected rows or columns, and the validation message. Do not include passwords or other sensitive account information when asking for help.
