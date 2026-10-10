---
title: "Import relationships from a template"
slug: "import-relationships-from-a-template"
summary: "Import connections between existing model objects using a relationship template."
category: "import-and-export"
nav_order: 7
status: published
keywords:
  - import relationships
  - endpoints
  - connections
related:
  - download-a-relationship-import-template
  - choose-managed-keys-for-import
  - relationship-types-and-relationships
  - understand-and-resolve-import-errors
updated: "2026-10-10"
---

# Import relationships from a template

Use a relationship import when you need to connect existing objects in a model using structured data. Each file targets one relationship type, and each row describes a connection using the fields in the generated template.

## Before you import

Download the template for the intended relationship type. Confirm that the objects at both ends of each connection already exist in the model and that the relationship type permits the connection.

Use the endpoint keys requested by the template. A relationship file cannot reliably refer to an object if its key is missing, misspelled or different from the key recorded in the model.

See [Download a relationship import template](/help/import-and-export/download-a-relationship-import-template/) and [Choose managed keys for import](/help/import-and-export/choose-managed-keys-for-import/).

## Run the import

1. Open the model's import workflow.
2. Select the relationship import option and the intended relationship type if prompted.
3. Choose the completed template file.
4. Review any validation feedback.
5. Submit the import using the available action.
6. Inspect the model to confirm that the expected connections are present and point in the intended direction.

Use the current labels in your OnyxJar environment; this guide deliberately avoids relying on button text that may change.

## Check the result

Check representative rows against the source data. Confirm that each relationship connects the correct source object to the correct target object, and that the chosen relationship type expresses the intended meaning.

A connection that is technically valid can still be semantically wrong if its endpoints are reversed or the wrong relationship type is used. Review meaning as well as whether the import completed.

## If the import is rejected

Check the endpoint keys, the selected relationship type, required columns and column order. Also confirm that the relationship type allows the selected source and target object types.

For more guidance, see [Understand and resolve import errors](/help/import-and-export/understand-and-resolve-import-errors/) and [Relationship types and relationships](/help/model-fundamentals/relationship-types-and-relationships/).
