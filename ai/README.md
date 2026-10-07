# AI (staged Assisted workflows)

Operation-agnostic AI substrate behind every Assisted operation. Principle:
**AI steps make semantic claims; OnyxJar (OJ) owns structure** -- canonical
state, ontology options and legality, identity matching, dependency closure,
compilation, reference resolution, policy, validation and commit. No stage
ever writes canonical data: the only output is a WORKING Proposal a human
reviews.

```
Reconcile:  Intent + evidence files
  [OJ]  sources              files -> addressable segments (headings, text blocks, list items, table rows)
  [AI]  extraction           segment batches -> IntentFrame + EvidenceGraph claims citing segments  (<=4 batches)
  [AI]  extraction_correction  invalid claims / uncovered or dismissed relevant segments, re-asked once (<=2 calls)
  [OJ]  analysis             ground -> normalise -> map -> identify -> targets/anchors -> ESC -> values -> coverage
                             -> WorkQueue (decision gaps / evidence gaps) -> route   (the convergence hub)
  [AI]  adjudication         open questions -> pinned option ids, citing segments  (only when needed, <=3 rounds)
  [AI]    (correction)       invalid answers re-asked once                         (<=2 calls, never a round)
  [AI]  gap_probe            evidence gaps -> re-extraction of OnyxJar-retrieved local packs (<=2 rounds)
  [AI]  gap_probe_correction invalid probe claims / missing verdicts, once (<=1 call)
  [OJ]  compile              blocked set -> ChangeSet v3 + ChangeTrace -> TracePolicy -> resolve -> stage
  [AI]  verification         objections, routed to the step that produced the cited decision (<=3 calls)
  [AI]    (correction)       an unroutable objection re-asked once (<=1 call)
  [OJ]  commit_proposal (final deterministic gate) -> Proposal (complete | partial)

  Every stage returns to analysis; any stage may create work for another, so
  Adjudication, Gap Probe and Verification are revisited until nothing new
  remains or a class's budget is spent (see Convergence).
Create:     [AI] planning (authors a ChangeSet v3) -> OJ resolve -> commit_proposal
```

A small input is typically 2 provider calls (one extraction batch + verification).

## Evidence lifecycle

- **Sources** (`services/sources.py`, readers in
  `assisted/services/evidence_extraction.py`). Each file becomes addressable
  segments with stable ids (`S1#4`, `S1#t2.r3`), heading paths, table headers
  and adjacency: PDF tables are recovered from text-run positions (a bold
  first row is a header), `.docx` tables natively, pipe/tab tables and
  headings/lists from text. An evidence *substrate*, not document
  understanding: it never interprets, and uncertain structure degrades to
  plain text blocks. Structural context is shown to the AI, never a claim.
- **Scale.** Evidence within `AI_EXTRACTION_BATCH_MAX_CHARS` is one
  Extraction call; larger evidence is extracted in batches of whole segments,
  given global ids at ingress and merged deterministically. A valid batch
  advances immediately; only defective items/segments are re-asked, packed
  together across batches in `extraction_correction` (its own budget), each
  at most once. Segments beyond the batch budget are recorded uncovered.
- **Ingress** (`reconcile/ingress.py`): the one path by which any AI
  response's claims (Extraction, corrections, Gap Probe, Verification
  `missed_evidence`) enter the graph. Provenance: `source_id` is the logical
  source and is derived from the cited `segment_id` (a segment named as a
  source is repaired; a segment of another source is rejected). Identity:
  ids in a response are local; OnyxJar owns flat global ids (a local id is
  kept if unused, else a fresh `e17`/`a42` -- never nested prefixes);
  identical duplicates collapse, a repeated known claim is a reference,
  conflicting duplicates are rejected precisely. Every claim's fate
  (accepted / repaired / collapsed / invalid / waiting / rejected / dropped /
  dropped_dependant, with the reason) is logged and ledgered as `ingest:`
  -- nothing is dropped silently.
- **Structure is citable, never quotable.** A segment's AI-facing form is its
  literal text plus `source_id` and `within` (ids of the heading/table
  segments it sits under); every payload includes those ancestor segments,
  so a heading or a table's header row is cited by its own id and text.
  Quoting a rendered heading path fails L1 as `context_not_quotable`.
- **Grounding** (`services/grounding.py`): L1 literal -- every excerpt
  occurs in its cited segment; L2 anchoring -- an entity's evidence mentions
  it, a fact's contains its value, an assertion's mentions both endpoints in
  one cited segment (`anchored`) or, with `support: structural`, in
  structurally related cited segments: a heading and an item under it, or the
  intent naming one end alongside the other's kind (`structural`); L3
  adequacy -- Verification, which sees the ledger's grounding decisions.
  Unanchored claims are refused at every entry point (Extraction, Gap Probe,
  Verification) and excluded by the analysis and TracePolicy.
  `support: structural` only changes which citations satisfy L2 -- never how
  a claim maps.
- **Correction gets a real anchor, never just the rejection.** An assertion
  rejected `unanchored_claim` can name an entity that *was* accepted (an
  entity's own grounding needs only its own name mentioned) while the
  relationship about it is not -- so a relational row can look "found" in
  the response and still be `uncovered` (coverage needs an assertion/fact,
  never an entity alone, for a row). Re-showing the model the segment it
  already (wrongly) cited does not fix this reliably. So the correction
  payload (`ExtractionCorrectionStage`/`GapProbeCorrectionStage`) adds
  `relationship_anchors` (`grounding.relationship_anchors`, via
  `extraction.correction_anchors`): `direct` (one segment stating both
  sides), `structural` (an ancestor/descendant pair, one naming each side --
  never a nearer heading that doesn't itself name the subject, rendered with
  its full containment via `segment_payload`/`with_ancestors`, never
  flattened to bare ids), or, when neither exists, `subject_only`/
  `object_only` -- a hint that no eligible anchor was found for *this* pair,
  not proof no relationship exists. It is strictly a locator: the model
  still proposes the claim and its own citation; grounding remains the sole
  authority on acceptance.
- **Coverage** (`reconcile/coverage.py`). Every segment that names a target
  or anchor (or, for rows/list items, a target type -- in its own text or its
  table's header row) is `claimed` (cited by a
  grounded claim; a relational table row only by an assertion or fact),
  `dismissed` (an AI coverage decision with a reason -- never a claim, never
  in the EvidenceGraph; dismissing a segment that names a target is re-asked
  once, then kept but flagged for Verification and the findings), or
  `uncovered` (re-asked once, then a warning and partial coverage).
- **Gap Probe** = targeted re-extraction. OnyxJar retrieves each unsatisfied
  requirement's own bounded evidence (segments naming the entity; the
  sections under a heading naming it, those whose heading names the
  counterpart's kind first; adjacent blocks; always their ancestor
  headings/tables; the claims already cited there), poses it as a question
  about the entity in catalogue names and descriptions (never keys, never a
  rule to satisfy), and the probe returns ordinary evidence claims (any hints
  stripped) plus a verdict per requirement. A `found` verdict must name
  accepted claims relating that entity, and stands only while one of them
  counts toward that requirement (re-checked by every analysis -- a venue
  named beside a stage does not give the stage a match); otherwise it is
  `found_unsupported`, and the requirement may be re-probed ONCE in a later
  round, told why the earlier answer did not count. Rows re-extracted whole
  usually satisfy cascading requirements in the same round. A `not_stated`
  verdict's coverage is the pack's.
- **Cardinality.** Requirements count distinct counterparts, never
  statements: two claims stating one relationship ("Eden Park hosts the
  match" / "the match is played at Eden Park") corroborate it -- one
  compiled change citing both, never a constraint conflict, never two of a
  minimum. Distinct satisfiers above a rule's maximum are never resolved by
  picking one: time-separated ones keep the single current one (or ask
  "which is current"); simultaneous ones are a `constraint_conflict` -- none
  compiled, never probed, a material finding suggesting a model change.
- **Honest blocking.** Each unmet requirement of a blocked item reports what
  the evidence states (`evidenced`, including claims whose mapping is still
  undecided) and what can be added (`viable`), why any undecided claims are
  undecided (`pending_decision`: not adjudicated / judged undecidable / answer
  refused), plus the cascade down to the root cause (e.g. ground <- fixture
  <- round: the round's competition is not evidenced), for the findings and
  Verification (which also receives the `open_decisions`).
- **Zero results are reviewed.** When nothing is compilable, Verification
  still runs with full objection routing (e.g. `missed_evidence` against an
  uncovered or dismissed segment re-enters the pipeline and can unblock
  targets); only an approval, unroutable/repeated objections or a spent
  budget ends `UNRESOLVED`.

## Intent targets are work

The intent is the authority for *what was asked*; evidence for *what
exists*. An explicit target ("the venues", "the stages") is a unit of
requested work, never just a filter on evidence -- so it can't vanish when
framing, mapping or extraction fails.

- **Framing is grounded in the intent** (`services/intent_frame.py`): L1, a
  target's excerpt is a verbatim span of the intent -- several targets may
  quote one span ("add the venues and stages"), and an excerpt elided with
  "..." whose fragments occur in order within one sentence is literally
  repaired to its covering span (`repair_elisions`, recorded as
  `repaired_from`); L2, the span names the target (its type label) or anchor.
  An element that still fails after its re-ask is **unframed**: kept
  (`ReconcileState.unframed`), reported as a block, shown to Verification,
  and restored by a `frame_error` amendment -- never deleted.
- **Every target ends in a status** (`Analysis.target_status`, ledgered
  `intent:<id>`, sent to Verification as `intent_targets`): `evidenced`
  (its items go through ESC as usual), `folded` (the catalogue's own word for
  relationships in general == `include_related`, lexical -- never made into a
  relationship type), `retire`, or a target-level **block**: `unframed`,
  `unmapped` (no catalogue kind -- reported, never fabricated), `undecided`,
  `not_evidenced`.
- **Missing evidence is recoverable work.** A mapped target with no evidenced
  item, or with target-relevant segments nothing accounted for (not claimed,
  not dismissed, not judged by a reviewer's retraction), is a **target gap**:
  an evidence gap probed at the level of its kind ("what do these segments
  say about venues?") over its own segments -- those labelled by the kind in
  their text, their table's header row or a heading above them (nothing
  labelled: the bounded document). Its `found` must name claims OnyxJar maps
  to that kind; `not_stated` is the only way to `not_evidenced` with
  complete coverage.
- **Scope.** Mapped targets seed ESC. Every evidenced item is a target only
  when the user named no kind at all (no targets, none unframed); an
  unmapped/unframed target never widens or empties scope.
- **Outcome.** `NO_CHANGE_REQUIRED` only when nothing is blocked -- every
  target evidenced and already consistent (or no targets). Any target-level
  block is handled by the partial-outcome rules: some changes -> partial;
  none -> `UNRESOLVED`.

## Convergence

Reconcile is a bounded, state-driven convergence process, not a pipeline
run once. `AnalysisStage` (`stages/reconcile_steps.py`) recomputes
everything from the claims after every stage and derives a **WorkQueue**:

- **decision gaps** -- open Adjudication questions (grouped: one question per
  predicate pattern between two kinds answers every claim of that wording).
  A requirement whose evidence exists but whose mapping is undecided
  (`Requirement.pending_decision`) is a decision gap, never an evidence gap:
  it is answered, not re-probed.
- **evidence gaps** -- target gaps (see "Intent targets are work") and
  unsatisfied requirements with no evidence at all,
  never probed (or one re-probe after an unsupported `found`).

`route()` sends decision gaps to Adjudication first (answers change which
requirements are truly unsatisfied), then evidence gaps to the Gap Probe,
then compiles; Verification objections become claims and re-enter at
analysis. So a probe's claims can raise questions, an answer can expose an
evidence gap, an objection can do either -- and each re-enters at the stage
that resolves it.

Bounds -- every class of work separately, and the run overall:

| Class | Counter | Setting |
|---|---|---|
| Extraction batches / corrections | `extraction` / `extraction_correction` | 4 / 2 |
| Adjudication rounds / corrections | `adjudication` / `adjudication_correction` | 3 / 2 |
| Gap Probe rounds / corrections | `gap_probe` / `gap_probe_correction` | 2 / 1 |
| Verification reviews / corrections | `verification` / `verification_correction` | 3 / 1 |
| All provider calls | `AI_WORKFLOW_MAX_PROVIDER_CALLS` | 14 (+1 explanation) |
| OnyxJar-only steps | `AI_WORKFLOW_MAX_DETERMINISTIC_STEPS` | 40 |

The engine charges a stage's `Correct` re-ask to `<stage>_correction` when
declared, so a correction never consumes a round. Termination: every route
needs NEW work (unasked question ids, unprobed requirement ids, unseen
objection fingerprints -- sets that only grow) and every class is bounded.

**Exhaustion is deferral, never a default.** A gap whose class budget is
spent writes no pin: the decision stays undecided (nothing resting on it
compiles), is ledgered `open:<question>` (`unadjudicated`, basis `budget`),
listed for Verification as an open decision, and reported as "not
adjudicated" -- never as "the evidence identifies 0". The only non-claim pin
is `rejected_answer` (an answer refused twice): never re-asked, and invisible
to mapping/identity/scope (`questions.claim_pins`), so it can never displace
a hint or lexical basis.

**Answers cite segments.** An Adjudication answer cites the segments it
rests on (`citations`: segment_id + that segment's verbatim text, a table
header and a row as two citations) or quotes the intent. Each question
carries its own segment_ids; the payload is those segments plus their
headings/tables. A reviewer's answer to a decision is validated the same way.

## Invariants

- **I1 Evidence.** The EvidenceGraph (`services/evidence_graph.py`) records
  what sources assert. It is never required to be ontology-valid and is never
  rewritten -- only appended to (Extraction, Gap Probe, Verification) or
  overlaid (clusters, mappings, identities, retractions). Its validator takes
  no index/catalogue, and the module may not import `ai.services.semantic`
  (`tests/test_evidence_graph.py`).
- **I2 Semantic claims.** OJ may derive structural consequences from explicit
  evidence claims and known ontology rules, but never creates a semantic
  claim that was not extracted from evidence or asserted by an AI step
  (Framing/Extraction, Adjudication, Gap Probe, Verification -- each with a
  verified excerpt). OJ computes options, legality, requirements and
  dependency edges, *selects* claimed items, compiles accepted claims, and
  applies lexical transformations of a claim (exact, unique, normalised name
  equality -- `basis: lexical`, flagged for Verification). It never chooses
  between options, reorients a predicate, infers an intermediate, picks a
  current value or a conflict winner, merges non-identical mentions, or
  creates anything because the ontology requires it. Enforced by the Decision
  Ledger (`kind: claim | structural`; every structural decision rests on a
  claim) and `reconcile/trace_policy.py` (every compiled action traced to
  grounded claim decisions). The ledger's third kind, `coverage` (dismissed
  and uncovered segments, probe verdicts), is a workflow record: it never
  counts as a claim.
- **I3 Mutation.** ChangeSet v3 (`services/change_set.py`) is a pure mutation
  contract: references, values, lifecycle, per-action `provenance` +
  `rationale` (which become the Proposal's EvidenceReferences). Links back to
  evidence live only in the ChangeTrace.
- **I4 Ambiguity.** Ambiguity is preserved -- `ambiguous` -> a typed question
  (always with an `undecidable` option) -> `unresolved_ambiguity` -- never
  converted to absence.

And, as before:

- **Every call is self-contained** (built from explicit `WorkflowState` /
  `ReconcileState`; no conversation memory).
- **Bounded.** Per-class budgets (rounds and corrections separately; see
  Convergence), `AI_WORKFLOW_MAX_PROVIDER_CALLS` (14) over all stage calls,
  the terminal explanation call outside it
  (`AI_TERMINAL_EXPLANATION_MAX_CALLS`, 1), and
  `AI_WORKFLOW_MAX_DETERMINISTIC_STEPS` over OJ-only steps. An item,
  question, probe or objection that fails the same way twice is dropped or
  recorded as refused, never re-asked.
- **No canonical UUIDs or viewer identifiers cross into AI context.**
- **Absence is never deletion.** Retirement needs an explicit
  `polarity: removed` claim *and* a confirmed `removal_confirmation` answer.
- **Conflicts are never silently resolved.** Differing values are classified
  (corroborated / distinct / superseded / candidate_conflict); an AI may only
  call a candidate conflict contradictory or distinct, never pick a winner; a
  `conflict` is never compiled.
- **Provenance is verified** everywhere (`services/provenance.py`), including
  on every ChangeSet action the resolver sees.

## Mapping, `indirect`, closure, partial outcomes

- **Mapping** (`reconcile/mapping.py`) offers every legal `(RelationshipType,
  orientation)` for an assertion's endpoint types and accepts one only on an
  explicit basis: `lexical`, `hint` (the extractor's hint *with its stated
  orientation*), or `adjudicated`. A hint legal only in the converse without
  a `converse` claim stays `ambiguous`. Same-type rules are flagged
  `orientation_unverifiable`.
- **`indirect`** decisions record `source` (what the evidence says),
  `mapping` (the path) and `reason`: `intermediate_unidentified` (the source
  refers to the intermediate only generically -- e.g. "Pool matches"),
  `no_direct_representation` (adjudicated direct statement the ontology can't
  hold), or `indirect_unclassified` (immaterial, not asked).
- **Evidence-Selective Closure** (`reconcile/scope.py`) derives the minimum
  rules of each new/reactivated entity and satisfies them only with mapped
  assertions between specific, identified entities. It selects; it never
  adds. Unsatisfied requirements go to the Gap Probe only when no evidence
  addresses them at all (never when the obstacle is an unresolved ambiguity
  or an undecided mapping -- those are decisions).
- **Partial outcomes.** `OperationPolicy.partial_outcome` (Reconcile:
  `allowed`; Create: `forbidden`). A blocked intent target and everything
  selected only to support it is not compiled; the rest is. The result is
  `READY_FOR_REVIEW` with `completeness="partial"` and `blocked_targets`
  (each also a material finding, and a "Not included" section in the
  Proposal summary). Nothing compilable -> `UNRESOLVED`. Verification is told
  about blocks and may object to a block itself, but never to its absence.

## Layout

| Path | Purpose |
|---|---|
| `services/orchestrator.py` | `run_ai_operation`: validate, open `AIExecution`, run the workflow, map to `OperationResult` |
| `services/workflow/engine.py` | Generic staged engine: AI stages + `DeterministicStage`s, budgets, the provider choke point, step recording |
| `services/stages/` | `extraction` (+ correction), `reconcile_steps` (analysis/compile), `adjudication`, `gap_probe` (+ correction), `verification`, `planning` (Create), `commit`, prompts |
| `services/sources.py`, `evidence_bundle.py` | Addressable evidence segments; mention/value matching |
| `services/reconcile/ingress.py` | Provenance normalisation, global evidence ids, duplicate handling, fate log |
| `services/tracing.py` | Opt-in dev tracing (`AI_TRACE_DIR`), `ReplayProvider`, `fate_table` |
| `services/evidence_graph.py`, `intent_frame.py`, `grounding.py` | Evidence-side claim contracts (I1) and L2 grounding |
| `services/reconcile/` | The deterministic core: `ledger`, `normalise`, `mapping`, `identity`, `scope` (targets/anchors/ESC/removals), `coverage`, `analysis`, `questions`, `near_miss` (probe retrieval), `compiler`, `trace_policy`, `responses` (AI response schemas), `state` |
| `services/change_set.py` | ChangeSet v3 (I3) |
| `services/resolution.py` | ChangeSet -> UUID ProposalChange specs; references, keys, duplicates, representability, policy, provenance |
| `services/staging.py` | `stage_and_validate` (speculative, rolled back) and `commit_proposal` |
| `services/semantic/` | `SemanticModelIndex`, catalogue, records, Create's bounded context |
| `services/provenance.py`, `feedback.py` | Excerpt verification; `AIIssue` and validation-issue translation |
| `models.py` | `AIExecution` and per-step `AIExecutionStep` (provider and deterministic; digests and codes only) |

## Testing

Deterministic core, no provider: `tests/test_reconcile_pipeline.py`,
`tests/test_evidence_graph.py`, `tests/test_sources.py`,
`tests/test_resolution.py`. Scripted-provider end to end:
`tests/test_reconcile_workflow.py` and `tests/test_evidence_lifecycle.py`
(the international flyer PDF in `tests/fixtures/`: table recovery through the
coverage gate, cascading requirements, constraint conflicts, zero-result
review). The real-provider runs are opt-in and print what to measure:
`ONYXJAR_LIVE_AI_TESTS=1 python manage.py test ai.tests.test_reconcile_workflow.LiveRugbyTests ai.tests.test_evidence_lifecycle.LiveInternationalFlyerTests`.

## Known limitations / follow-ups

- Investigating a live run: set `AI_TRACE_DIR` (dev only; files on disk,
  never the database) to capture every step's payload/output and a state
  snapshot (pins with their basis, open questions, probe requests, and the
  routed WorkQueue); replay it with `tracing.ReplayProvider` -- strictly, or
  by stage with `inject` outputs for calls the captured run never made (a
  counterfactual, e.g. the extra Adjudication rounds of a re-routed run; see
  `tests/test_reconcile_convergence.py`); `tracing.fate_table` lists every
  claim's ingress / grounding / mapping / scope fate. From Git Bash on
  Windows, pass `MSYS_NO_PATHCONV=1` to `docker exec` so `/app/...` paths
  are not rewritten.
- PDF structure comes from PyPDF2 text-run positions: robust for generated
  documents, unmeasured on scanned or unusual layouts (they degrade to text
  blocks). Catalogue slicing and coreference at scale are later work.
- Coverage relevance is lexical (names, aliases, target type labels):
  paraphrased mentions are missed and generic paragraphs may be re-asked;
  measure re-ask and flagged-dismissal rates on live runs.
- Reconcile proposes data changes only (schema-need compilation is deferred:
  unrepresentable facts/relationships are findings).
- `SemanticModelIndex.load` reads the whole model and staging validates the
  whole model -- query-backed lookups and scoped validation are later work.
- Cardinality validation counts all active relationships (ignores validity
  windows), so time-separated satisfiers above a maximum compile only the
  current one.
- Token usage of transport-level retries that fail inside `OpenAIProvider` is
  not reported by the SDK and so is not counted; plan allowance is checked
  when a task starts, not between stages.
