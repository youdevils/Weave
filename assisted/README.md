# Assisted

Durable, user-facing record of an "Assisted" operation (product terminology:
**Assisted**, never "AI"). Wraps the `ai` app's orchestration substrate
(`AIExecution`, `run_ai_operation`, the operation registry, the Proposal
compiler) without duplicating it, and never replaces the normal human-review
`Proposal` pipeline.

```
setup form -> AssistedTask(QUEUED) -> Celery -> run_ai_operation()
   -> outcome policy -> READY_FOR_REVIEW | FAILED
   -> (model.signals.proposal_committed / proposal_abandoned) -> COMPLETED | FAILED
```

## Rules that must keep holding

- **One active Assisted operation per Model.** `AssistedTask.ACTIVE_STATUSES`
  = QUEUED/RUNNING/READY_FOR_REVIEW. Enforced by locking the Model row before
  checking/creating (`assisted.services.lifecycle.start_assisted_create`),
  the same pattern `ProposalService.create_working` and `delete_model` use,
  backed by a Postgres partial unique constraint
  (`unique_active_assisted_task_per_model`) as defense-in-depth.
- **Never duplicate `AIExecution`'s payloads.** `AssistedTask` only ever
  stores small denormalized fields (status, outcome, failure reason,
  counters) -- never raw prompts/context/provider responses. This matters
  because `ai.AIExecution.model` is `CASCADE` (not `SET_NULL`): an
  `AIExecution` row is hard-deleted along with its Model on a failed Create,
  so anything `AssistedTask` needs to survive that must already be
  denormalized onto itself *before* the Model is deleted.
- **The AI-outcome -> AssistedTask mapping is a per-operation policy**
  (`assisted.services.outcome_policy`), not a global switch -- Create
  requires a Proposal for every success path; a future Assess would not.
- **Failure cleanup is operation-gated.** `assisted.services.cleanup.fail_task`
  is the single place a task reaches `FAILED`, called from both the Celery
  path and the lazy stale-reclaim path. It deletes the Model only for
  `AssistedTask.BOOTSTRAP_MODEL_OPERATIONS` (today: `CREATE`) -- Reconcile/
  Change/Assess operate against a Model that pre-existed the task and must
  never be touched by a failed task.
- **`proposal_committed`/`proposal_abandoned` are synchronous domain
  signals**, not commit-notification plumbing -- see `model/signals.py` for
  why they fire inside the same transaction as the Proposal transition
  itself, before any FK is nulled.

## Layout

| Path | Purpose |
|---|---|
| `models.py` | `AssistedTask`, `AssistedTaskEvidence` |
| `services/lifecycle.py` | `start_assisted_create`, one-active-task enforcement, lazy stale reclaim |
| `services/execution.py` | Celery-worker side: claim, run the orchestrator, interpret the result |
| `services/outcome_policy.py` | Per-operation AI-outcome -> AssistedTask mapping |
| `services/cleanup.py` | Shared terminal-FAILED transition + operation-gated Model deletion |
| `services/evidence.py` | Evidence file validation/storage |
| `services/evidence_extraction.py` | Evidence text extraction (plain text/PDF/.docx), reused by both upload-time validation and worker-time AI ingestion |
| `uploads.py` | Per-file upload size limiting (duplicated from `ingestion.uploads`) |
| `signals.py` | Receivers for `model.signals.proposal_committed` / `proposal_abandoned` |
| `tasks.py` | The one Celery task, `run_assisted_operation` (shared by every Assisted operation) |

## Known limitations

- Stale-task reclaim is lazy only (checked inline before starting a new
  task, or by the `delete_model_view` guard) -- there is no Celery-beat
  sweep, matching the rest of this codebase's convention.
- Evidence is limited to plain text, PDF, and `.docx` -- anything else is
  rejected at upload time (`services/evidence_extraction.py`). There is no
  OCR layer, so a scanned (image-only) PDF extracts no text.
- The guard against deleting a Model with an active AssistedTask lives in
  `workspace` (`delete_model_view`), not in `model.services.model_deletion`,
  since `delete_model`'s only callers are already in `workspace`.
