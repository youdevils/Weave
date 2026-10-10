---
title: "Prepare data for import"
slug: "prepare-data-for-import"
summary: "Prepare an import file that matches the selected OnyxJar template."
category: "import-and-export"
nav_order: 2
status: published
keywords:
  - spreadsheet
  - columns
  - keys
  - data preparation
related:
  - import-and-export-overview
  - download-an-object-import-template
  - download-a-relationship-import-template
  - choose-managed-keys-for-import
updated: "2026-10-10"
---

# Prepare data for import

The most reliable way to prepare an OnyxJar import is to start with the template generated for the type of content you want to import. The template defines the expected columns and their order.

## Start with the correct template

Use an object template for one object type or a relationship template for one relationship type. These are separate workflows: an object row describes an item in the model, while a relationship row connects existing items.

Do not create a generic spreadsheet and assume OnyxJar can infer its structure from the column headings. The importer maps values by **column position**, so the order of the columns matters. Keep the template's columns in place, even if you would prefer different headings or a different order.

## Keep each file focused

A single import file targets one object type or one relationship type. Do not combine rows for multiple types in the same file. Obtain the matching template for each type you need to import.

For Excel workbooks, use a single worksheet per import file. Workbooks with multiple sheets are not accepted by the current importer.

## Check the values

Before importing, check that:

- each row represents the intended object or relationship;
- required fields have values in the expected columns;
- values match the permitted formats or choices for the relevant attributes;
- object and type references use the managed keys expected by the template;
- relationship endpoints refer to objects that exist in the target model; and
- columns have not been inserted, deleted or rearranged.

For background on the keys used in these files, see [Choose managed keys for import](/help/import-and-export/choose-managed-keys-for-import/).

## Preserve the source data

Keep a copy of the original source file and work on a prepared copy. If the importer reports a problem, correct the source data and try again rather than making unrelated changes to the model to work around a malformed file.

## A practical preparation sequence

1. Download the template for the target type.
2. Copy your source values into the corresponding template columns.
3. Check the first few rows against the original source.
4. Confirm the column order and worksheet count.
5. Check keys and values before submitting the import.

If the import fails, [Understand and resolve import errors](/help/import-and-export/understand-and-resolve-import-errors/) explains common causes to investigate.
