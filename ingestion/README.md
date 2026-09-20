# Data Import

Data Import populates an **existing canonical model** from one structured file (CSV, XLSX or legacy XLS).
It is reached from **Assets** in the model sidebar.

```
upload ─► target ─► map ─► preview ─► ONE Working Proposal ─► (existing) review ─► validate ─► commit
   │                                        │
   └─ ImportSource (bytes, in the DB)       └─ a ProposalChange per actual change, each with an
                                               EvidenceReference whose source = the stored file name
```

Import decides only **what ProposalChanges the source represents**. Whether those changes are *allowed* is the
existing Proposal validator's job (`model.services.validation`), which Import never imports (asserted in
`tests/test_architecture.py`). Import never writes canonical data and never touches the ontology.

## Rules that must keep holding

- **One import = one Proposal**, created in one transaction under the Model row lock (which also makes the
  live-proposal cap race-free). Zero changes ⇒ no proposal, no changes, no evidence, source deleted.
- **Blocking, not skipping.** A row whose identity cannot be determined (unresolved, ambiguous, mismatched,
  unreadable id/endpoint) blocks the whole import. Nothing partial is ever created.
- **Canonical only.** Matching reads `Object` / `Relationship` tables. Other proposals are never consulted.
- **Identity is explicit and exact:** a Weave Object/Relationship ID, or one attribute the user marks "use to
  identify" (trimmed once, compared case-sensitively and type-strictly). Names are never matched. Weave Keys do not
  exist; the resolvers are where they would be added.
- **The match attribute is never updated on an existing object** (even when its cell is blank); it is written on CREATE.
- **Later rows win**, blank is a real assignment, and only *canonical-before → final-after* changes are emitted.
- **Relationship direction is part of identity.** Endpoints are cross-checks only when a relationship id is given.
- **No deletion or sync semantics.** Import is CREATE / UPDATE / NO-OP.
- **Blank:** UPDATE ⇒ `null` (`""` for name/description); CREATE ⇒ key omitted (as the record editors do).

## Layout

| Path | Purpose |
|---|---|
| `models.py` | `ImportSource` — the persisted upload (bytes in the DB, generated unique `stored_name`) |
| `services/parsing/` | CSV / XLSX / XLS → `ParsedTable` (one sheet, limits, never evaluates formulas) |
| `services/source_file.py` | Store/sanitise/stage/sweep uploaded sources |
| `services/targets.py`, `mapping.py` | Canonical targets and the validated, canonical mapping document |
| `services/coercion.py` | Cell → the JSON value a change carries (representation only) |
| `services/identity.py` | Exact attribute index and endpoint resolution |
| `services/object_planner.py`, `relationship_planner.py`, `plan.py`, `planner.py` | Rows → `ImportPlan` (changes, problems, summary) |
| `services/proposals.py` | The one transactional path that creates the proposal and evidence |
| `access.py`, `views.py`, `uploads.py`, `urls.py` | Owner/Editor only (Viewer 403, non-member 404); size limit on received bytes |
| `static/ingestion/js/` | The page: `import-api`, `-state` (pure), `-render` (escaping), `-boot` |

Existing services extended for this: `ProposalService.create_working / live_queryset / assert_capacity /
record_changes_bulk`, `EvidenceService.add_for_changes`, and `model.services.validation.fields` (built-in
Object/Relationship field checks, also applied as pre-checks in `submission._apply_create_or_update`, together with a
check that a relationship's endpoints still exist).

## Source lifecycle

Uploads are *staged* and private to their uploader. A new upload replaces the uploader's previous staged one;
staged sources older than 24 h are swept on the next upload. An import with changes stamps `imported_at` and records
its `proposal`; the source then lives as long as that proposal. Abandoning the proposal takes its evidence with it and
the next sweep removes the source. Discarding single changes or evidence keeps it. Deleting the model cascades.

## Limits (`IMPORT_*` in settings)

5 MB (enforced on bytes received), 2,000 data rows, 100 columns, 1,000 changes per import. The change cap is set by
the Proposal Review page, which renders every change (~13 KB of HTML each); raise it only with pagination there.

## Known limitations / deferred

- One worksheet, one target type per import; no mixed object + relationship imports; endpoints are never created.
- Composite identity, Weave Keys, export, a source list/download UI, background processing, persisted import jobs.
- No AI ingestion (the services are structured so it can reuse parsing, planning and proposal creation).
- Pre-existing hand-made objects with no identifying attribute cannot be matched (by design: no name matching);
  fill the attribute in first, or use their Weave ID.
