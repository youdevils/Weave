# Data Import

Data Import populates an **existing canonical model** from one structured file (CSV, XLSX or legacy XLS).
It is reached from **Import/Export** in the model sidebar (the page is titled *Import & Export*), presented as a five-step guided workflow alongside Model Export (see `services/model_export.py`).

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
- **Identity is explicit and exact.** For objects, the normal column is the object's OnyxJar Key (assigned by the
  application; never user-typed). A key cell that matches an existing object's key updates it; one that matches
  nothing blocks the import; a blank cell creates a new object and leaves the application to assign its key. The
  internal Database ID and a user-marked "use to identify" attribute remain available as advanced/optional
  alternatives (trimmed once, compared case-sensitively and type-strictly). Names are never matched.
- **Relationship endpoints resolve by object key**, searched across every object type the relationship's rules
  allow on that side. Found in exactly one candidate type ⇒ resolved. Found in zero ⇒ blocked
  (`unresolved_endpoint`). **Found in more than one ⇒ blocked (`ambiguous_endpoint_key`), never guessed** — map the
  column to one specific type (pin it), or make the key unique across those types. Once both endpoints resolve, the
  pair is checked against the relationship type's actual allowed `(subject_type, object_type)` pairs — each side
  being individually valid does not mean the pair is permitted. Database ID remains an advanced/optional column.
- **The match attribute is never updated on an existing object** (even when its cell is blank); it is written on CREATE.
- **Later rows win**, blank is a real assignment, and only *canonical-before → final-after* changes are emitted.
- **Relationship direction is part of identity.** A relationship's identity is its type plus its resolved
  `(source, target)` endpoints — it has no key of its own.
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
| `services/identity.py` | Key/attribute indexes and endpoint resolution |
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
- Composite identity, a source list/download UI, background processing, persisted import jobs.
- Model Export (`services/model_export.py`) is all-or-nothing: no filters, no object selection, and nothing yet reads its JSON back in.
- No AI ingestion (the services are structured so it can reuse parsing, planning and proposal creation).
- Relationships have no key of their own (by design — their identity is their type plus their endpoints); objects
  with no key, no identifying attribute and an unknown Database ID cannot be matched (by design: no name matching).
