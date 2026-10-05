# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Dev environment runs via Docker Compose (Postgres, Redis, Django, Celery):

```
docker compose -f docker-compose.dev.yml up
```

This starts `web` (Django dev server on :8000), `db` (Postgres 15), `redis`, and `celery_worker`.
Requires `.env.dev` (already present) — `onyxjar/settings.py` raises `RuntimeError` at import
time if `SECRET_KEY` or `RESEND_API_KEY` are unset, so any bare `python manage.py ...` outside
the container needs the same env vars loaded.

Tests:

```
python manage.py test                        # all Django tests
python manage.py test ingestion               # one app
python manage.py test ingestion.tests.test_duplicates.SomeTestCase.test_method  # single test
npm test                                      # JS unit tests (Node's built-in runner)
```

`npm test` runs `viewer/jstests/`, `model/jstests/`, `publication/jstests/`,
`ingestion/jstests/`, and `website/jstests/` in one pass (see `package.json`).

Publication ships a golden-file parity suite that keeps the Python graph engine and its JS port
in sync (`publication/tests/test_parity.py` vs `model/static/model/js/explore/engine/`). If you
change `model/services/model_graph/` on purpose, regenerate both sides:

```
ONYXJAR_UPDATE_PARITY=1 python manage.py test publication.tests.test_parity
npm test
```

## Architecture

Django 5.2 + DRF + Celery monolith, apps listed in `onyxjar/settings.py` `INSTALLED_APPS`:
`account`, `model`, `ai`, `assisted`, `api`, `ingestion`, `publication`, `viewer`, `website`,
`workspace`. `api` is currently an empty scaffold (stub `views.py`, no real code yet) — its URLs
aren't even wired into `onyxjar/urls.py`. `ai` is **not** a scaffold: it's a fully-built,
operation-agnostic AI orchestration substrate (`ai/services/orchestrator.py::run_ai_operation`,
a `ChangePlan`/`AIStructuredResult` schema, bounded refinement/context-expansion, the Proposal
compiler) that any Assisted operation plugs into via one `OperationDefinition`
(`ai/services/operations.py`), registered in `ai/services/operation_definitions.py`. `assisted`
is the user-facing wrapper around it — `AssistedTask`/`AssistedTaskEvidence`, per-operation
lifecycle/outcome-policy services, and the Assisted Work UI (landing/entry/task-detail pages).
As of this writing, CREATE and RECONCILE are real; CHANGE and ASSESS are registered as
`AssistedTask.Operation` choices but still stubbed at the view layer
(`assisted/views.py::change_entry`/`assess_entry`). Routing note: `publication` and `ingestion`
are both mounted under the `/model/` prefix alongside `model` itself.

### Canonical data model

`workspace` provides multi-tenancy: a `Workspace` has `WorkspaceMember`s with role
`owner` / `editor` / `viewer`. Each workspace owns one or more `model.Model`s. Within a Model,
the canonical graph is `ObjectType`/`Object` and `RelationshipType`/`Relationship`, with
`AttributeDefinition`s and free-form JSON `attributes`. **Canonical data is never written
directly** — all changes flow through a `Proposal` → `ProposalChange` review pipeline
(`model/services/proposal/`, validated by `model/services/validation/`), which is what the
Owner/Editor/Viewer roles gate. `account.CustomUser` is a custom email-based user model
(`AUTH_USER_MODEL`), separate from the public website's own stub login pages (see below).

Three subsystems build on top of that canonical model, each with a detailed README you should
read before touching it rather than re-deriving the rules from code:

- **Import** (`ingestion/README.md`) — turns an uploaded CSV/XLSX into exactly one Proposal.
  Blocks the whole import on any unresolved identity rather than partially importing; never
  writes canonical data or the ontology directly.
- **Publishing** (`publication/README.md`) — turns one canonical revision into a self-contained,
  immutable, offline HTML "Portable Explorer" file. The HTML is generated in memory and never
  stored server-side.
- **Viewer** (`viewer/contracts.py`) — a domain-agnostic rendering runtime. Hard architectural
  boundary: `viewer` must never import from `model` or `publication`, or reference the Django
  ORM — everything it renders must travel through the versioned JSON payload contract defined
  there (`SCHEMA_VERSION`). Both the live Explorer and the published HTML file share this same
  runtime.

Settings for tunable business rules (proposal staleness thresholds, live-proposal caps, import
size/row/column limits, website contact-form recipient, etc.) live in namespaced blocks near the
bottom of `onyxjar/settings.py` (`PROPOSAL_*`, `IMPORT_*`, `WEBSITE_*`) — check there before
hardcoding a limit in app code.

### Public website vs. app

`website` is the public marketing site (`/`, `/examples/`, `/privacy/`, `/terms/`, `/contact/`).
Its `/login/` and `/signup/` pages are **intentionally-stubbed views** living in the `account`
app (`account:login`, `account:signup`) that never create a session — `settings.LOGIN_URL`
points at `account:login` so `@login_required` redirects there. The real authenticated
application lives under `/workspace/`. See `website/README.md` for the design-token system
(`static/website/css/onyxjar.css`) and brand asset locations.
