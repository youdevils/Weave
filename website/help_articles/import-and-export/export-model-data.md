---
title: "Export model data"
slug: "export-model-data"
summary: "Take supported model data out of OnyxJar and understand what export is for."
category: "import-and-export"
nav_order: 9
status: published
keywords:
  - export
  - model data
  - download
related:
  - import-and-export-overview
  - understand-and-resolve-import-errors
updated: "2026-10-10"
---

# Export model data

Exporting model data lets you take supported information out of OnyxJar for inspection or further use. It is different from publishing a model for readers to explore.

## Export model data

Open the model and use the model-data export option provided by your current OnyxJar interface. Follow the format and options presented there, then save the resulting file where you can identify which model and point in time it came from.

Because the exact export choices can evolve, use the current UI and the downloaded file as the source of truth for its format and contents. Do not assume that a field, relationship or metadata item is included unless it is represented in the export.

## Keep the export useful

For work that may be repeated, keep the exported file with a note of the model and when it was created. If you transform the file in another tool, preserve an unmodified copy so you can compare later changes with the original output.

Before relying on an export for a specific purpose, inspect it and confirm that it contains the information you need. A file that is suitable for analysis or data handling may not be a complete record of every part of the OnyxJar experience.

## Export is not publishing

A model-data export is intended for working with model data outside the normal editing interface. Publishing creates an interactive, read-only HTML snapshot so others can explore a model without editing it. The snapshot reflects the model at the time it was published and does not automatically update when the model changes.

Choose export when you need the data; choose publishing when you want to share an explorable view.

## Export is not a full restore workflow

Do not treat a model-data export as a complete application backup or assume it can be uploaded to recreate a model. Full model import/restore is a separate capability and should only be relied on if OnyxJar explicitly provides and documents it.

See [Import and export overview](/help/import-and-export/import-and-export-overview/) for help choosing the right workflow.
