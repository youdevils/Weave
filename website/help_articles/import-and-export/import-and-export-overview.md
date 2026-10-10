---
title: "Import and export overview"
slug: "import-and-export-overview"
summary: "Choose the right workflow for moving model data into or out of OnyxJar."
category: "import-and-export"
nav_order: 1
status: published
keywords:
  - import
  - export
  - templates
  - model data
related:
  - prepare-data-for-import
  - import-objects-from-a-template
  - import-relationships-from-a-template
  - export-model-data
updated: "2026-10-10"
---

# Import and export overview

OnyxJar provides workflows for bringing structured information into a model and taking model data out. The right workflow depends on whether you are adding or updating model content, or sharing a view of the model with other people.

## Choose the workflow you need

- **Import model data** when you have structured data to add to a model. Use the relevant template for the object type or relationship type you are working with.
- **Export model data** when you need to take supported model data out of OnyxJar for inspection or use elsewhere.
- **Publish a model** when you want other people to explore a read-only view. Publishing creates an interactive HTML snapshot; it is different from exporting model data.

An exported data file and a published HTML snapshot serve different purposes. One is model data; the other is a reader-friendly view of the model at publication time.

## How imports are organised

An import file targets one kind of model content. An object import targets an object type; a relationship import targets a relationship type. Use the matching template rather than combining unrelated object and relationship rows in a single file.

The generated templates are the best starting point because they reflect the fields expected for the selected type. Keep the columns in their original order and use the managed keys supplied by OnyxJar where the template requires them.

## Before you import

1. Identify the object type or relationship type you want to work with.
2. Obtain its current import template.
3. Prepare the data using the template's columns and order.
4. Check keys, required values and references before running the import.
5. Review the result and correct any reported problems in the source file.

See [Prepare data for import](/help/import-and-export/prepare-data-for-import/) before preparing a larger file.

## What import and export do not mean

Importing data into a model is not the same as restoring a complete application backup. Do not assume that an export can be imported to recreate every aspect of a model or account unless OnyxJar explicitly supports that workflow.

Likewise, exporting model data is not the same as publishing a portable HTML view. Choose the workflow based on what you need to do with the result.

## Where to go next

- [Import objects from a template](/help/import-and-export/import-objects-from-a-template/)
- [Import relationships from a template](/help/import-and-export/import-relationships-from-a-template/)
- [Export model data](/help/import-and-export/export-model-data/)
