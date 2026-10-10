---
title: "Troubleshoot unexpected model data"
slug: "troubleshoot-unexpected-model-data"
summary: "Investigate missing objects, missing relationships, or values that do not match what you expected."
category: "account-and-troubleshooting"
nav_order: 2
status: published
keywords:
  - missing object
  - missing relationship
  - unexpected data
  - import troubleshooting
related:
  - create-and-edit-objects
  - create-and-edit-relationships
  - import-objects-from-a-template
  - import-relationships-from-a-template
updated: "2026-10-10"
---

# Troubleshoot unexpected model data

If a model does not look the way you expected, narrow the problem down before changing anything. An object may be present but outside the current graph view, a relationship may not have been created, or a value may differ from the source you were working from.

## 1. Make sure you are looking at the right model and view

Confirm that you opened the intended model. In Model Explorer or the graph, check whether a search term, object-type filter, relationship-type filter, or current selection is narrowing what you can see.

A filtered view does not necessarily mean data is missing from the underlying model. Clear filters or broaden the view, then search for the specific item again.

## 2. Check the object itself

If an object is missing, search for it by name and inspect the relevant object type. Check for small differences in spelling or naming, and consider whether the item was created under a different type than you expected.

If the object exists but its details are wrong, open its details and inspect the relevant attributes. Compare the value with the source information you intended to record.

For editing guidance, see [Create and edit objects](/help/build-and-maintain-models/create-and-edit-objects/) and [Update object attributes safely](/help/build-and-maintain-models/update-object-attributes-safely/).

## 3. Check the relationship and its endpoints

If a connection is missing, confirm that both endpoint objects exist. Then check the relationship type and the direction of the connection. A connection from A to B is not always equivalent to a connection from B to A.

If you were trying to create the relationship manually, check that the selected relationship type is valid for those endpoint object types and that any required relationship attributes have valid values.

See [Create and edit relationships](/help/build-and-maintain-models/create-and-edit-relationships/) for the normal workflow.

## 4. If the data came from an import

Compare the affected item with the source file you uploaded. Check that the row is present, the relevant values are in the expected columns, and any keys used to identify objects or relationship endpoints match the intended records.

Review the import result and any reported errors. Do not assume that every row in a source file was accepted simply because the import process finished. Correct the source data where necessary and run the appropriate import again.

For detailed guidance, see [Import objects from a template](/help/import-and-export/import-objects-from-a-template/), [Import relationships from a template](/help/import-and-export/import-relationships-from-a-template/), and [Understand and resolve import errors](/help/import-and-export/understand-and-resolve-import-errors/).

## 5. Change one thing at a time

Once you have found a likely cause, make a focused correction and check the result. Avoid making several unrelated changes at once; it becomes harder to tell which change resolved the issue.

If the problem remains, record the model, the affected object or relationship, what you expected, what you observed, and the steps you took. Include the relevant source row or error message where applicable, but do not share passwords or other credentials.
