---
title: "Download a relationship import template"
slug: "download-a-relationship-import-template"
summary: "Get the template for importing connections of a specific relationship type."
category: "import-and-export"
nav_order: 6
status: published
keywords:
  - relationship template
  - connection import
  - download template
related:
  - prepare-data-for-import
  - import-relationships-from-a-template
  - choose-managed-keys-for-import
updated: "2026-10-10"
---

# Download a relationship import template

A relationship import describes connections between objects that are already represented in the model. Use the template for the relationship type you want to add.

## Choose the relationship type

Open the model's import workflow and select the relationship-template option. Choose the relationship type that describes the connections you need to represent, then download the template supplied by OnyxJar.

The relationship type matters because it defines what a connection means and which object types can be connected. For background, see [Relationship types and relationships](/help/model-fundamentals/relationship-types-and-relationships/).

## Understand the endpoints

A relationship connects a source object to a target object. The generated template indicates how to provide the references for those endpoints and any other required fields. Use the managed keys expected by the template; don't rely on display names where a key is required.

The direction of a relationship can matter. Check which endpoint is the source and which is the target rather than assuming a connection works the same way in both directions.

## Keep the file structure intact

The importer maps values by column position, so leave the template's columns in their original order. One import file targets one relationship type. If you need to import more than one type, prepare a separate file for each type.

For Excel workbooks, use a single worksheet per import file.

## Next step

Add the intended relationships to the template, check that the endpoint keys refer to existing objects, and follow [Import relationships from a template](/help/import-and-export/import-relationships-from-a-template/).
