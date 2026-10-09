# RECONCILE architecture investigation and migration plan (hardened)

## Context

Many iterations have gone into fixing individual Reconcile failures: extraction, correction, coverage, probes, adjudication, verification and their contracts. Live runs on the international flyer still fail. You asked whether the architecture itself is wrong, and specifically to test this hypothesis: *separate deterministic document normalisation from semantic interpretation, and both from deterministic governance*.

This is an investigation and planning document. No code was changed. This revision hardens the first version of the plan:
- explicit DEM and Reading invariants;
- Reading identity and lifecycle;
- distinct negative states;
- application safety;
- causal Verification;
- a regression matrix;
- sharper acceptance criteria per phase.

**Baseline note.** The `not_stated` / `not_stated_contested` safeguard (labelled-evidence contest plus one re-probe) is already implemented and complete. It is part of the **legacy baseline** this assessment was made against, not unfinished migration work. It stays fully operational in claims mode until Phase 6.

**What I examined:**
- the whole `ai/` Reconcile path;
- the raw local trace `.ai-traces/24063e61…`, which includes payloads and snapshots;
- the fixture outputs for `10390789`, `286357bd`, `3f801647`, `7f0fcac7`, `f3e0d659`, `1d854489`;
- `replay_baseline.json`;
- the test suite;
- the assisted/persistence interfaces.

---

## 0. Empirical baseline: what the seven flyer runs did

| Run | Calls | Outcome | Changes | Verification payload | Verification verdict |
|---|---|---|---|---|---|
| 24063e61 | 7 | UNRESOLVED | 0 | 84.6k chars (58.7k ledger, 163 decisions) | approved |
| 10390789 | 13 | UNRESOLVED | 0 | 141.5k | approved |
| 286357bd | 9 | UNRESOLVED | 0 | 90.1k | approved |
| 3f801647 | 11 | UNRESOLVED | 0 | 120.9k | approved_with_findings (6 missed_evidence, all filed as *info*) |
| 7f0fcac7 | 12 | UNRESOLVED | 0 | 137.5k | approved_with_findings (fixture rows missed, filed as *minor*) |
| f3e0d659 | 13 | UNRESOLVED | 0 | 206.0k | approved_with_findings |
| 1d854489 | 13 | UNRESOLVED | 0 | 132.3k | approved |

Total payload is roughly 190k–415k chars per run, plus about 8–9.5k chars of system prompt and about 7.7k chars of schema on every call. Every run produced nothing, and every Verification pass approved that.

### What the flyer says

The flyer is about 7k chars over 24 segments.

**Tables:**
- `t1` has no header. Its rows are `Pool A | New Zealand | Fiji | Japan | Samoa` and the same for Pool B. It sits under the "Teams" heading, which sits under the title heading S1#1.
- `t2`: `Venue | Location | Primary use`, 6 rows.
- `t3`: `Stage | Match | Venue`, 4 pool fixtures.
- `t4`: `Stage | Match | Venue`, 2 quarter-final fixtures, for example `Quarter-final | Pool A winner v Pool B runner-up | Orangetheory Stadium`.

**Prose:** the format list S1#7–S1#10 ("Pool Stage: …", "Quarter-finals: …", "Final: … at Eden Park, Auckland") and a facts list.

### Reference outcome (used by the Phase 0 oracle)

I derived this by hand from the catalogue rules, taking the Pool A and Pool B rows as Stages.
- **Compiled (a partial proposal):**
  - the tournament, Pool A and Pool B;
  - 4 pool matches;
  - 8 teams;
  - Eden Park, Sky Stadium, Forsyth Barr and FMG Waikato.
- **Blocked:**
  - Quarter-finals and Orangetheory Stadium. Both depend on the QF fixtures, whose participants are unidentified, while `has_team` requires exactly 2 identified teams.
  - Semi-finals and Final: no fixtures are listed for them.
  - McLean Park: no fixture names it.

The question of whether "Final … at Eden Park" counts as a match is semantic and stays an explicit question.

---

## 1. Current architecture (component and data-flow map)

```
AssistedTaskEvidence(bytes) --extract_text/_pdf_blocks (assisted/services/evidence_extraction.py)--> blocks
  --sources.build_segments--> Segment{id,kind,text,heading_path,ancestor_ids,header,cells}   [rebuilt every run, never persisted]
  --EvidenceBundle (evidence_bundle.py)
[AI] Extraction (stages/extraction.py, prompts.EXTRACTION+CLAIM_CONTRACT)
     payload: intent + full catalogue + Segment.context() = {id,kind,text,within}   <-- cells/header NOT exposed as structure
     output : IntentFrame + EvidenceGraph{entities,assertions(free-text predicate),facts} + dismissed_segments (one per segment)
  -> ingress.ingest (ids, provenance repair, dup collapse, fate log)
  -> validate_evidence_graph (I1) + grounding.grounding_issues (L2: lexical mentions in cited text; structural = ancestor relation)
  -> coverage.compute_coverage (lexical relevance; claimed/dismissed/uncovered; "unaccounted" names)
[AI] Extraction correction (<=2 waves): invalid items (+relationship_anchors locator), uncovered/flagged segments
[OJ] Analysis (reconcile/analysis.run_analysis, recomputed from scratch each visit):
     ground -> normalise(build_clusters) -> mapping(pin|hint|lexical, else question) -> identity -> targets/anchors
     -> scope.evidence_selective_closure (Requirements, cascade) -> values -> coverage -> questions(10 kinds)
     -> probe verdict checks (found_unsupported, not_stated_contested) -> target gaps -> WorkQueue
[OJ] route(): decision gaps -> Adjudication; evidence gaps -> Gap Probe; else Compile
[AI] Adjudication: questions -> pinned option ids with segment citations (+1 correction/round)
[AI] Gap Probe (+ near_miss packs): per-requirement packs -> claims + verdicts
     near_miss.labelled_evidence ("row cell IS entity under header naming the kind") -> contests a not_stated, one re-probe
[AI] Gap Probe correction
[OJ] Compile (compiler -> ChangeSet v3 + ChangeTrace) -> trace_policy.check_trace -> resolution -> staging (rolled back)
[AI] Verification: intent, frame, all segments, dismissed/uncovered, WHOLE decision ledger, changes, delta,
     blocked_targets cascades, intent_targets, open_decisions, rejected_claims, notes -> objections routed to decision steps
[OJ] commit_proposal -> Proposal + ProposalChange + EvidenceReference(source=file name, locator=segment id, note=excerpt)
Tracing: tracing.py (payload+output+snapshot per step), ReplayProvider; EquivalenceReplay/IdTranslatingReplay in tests
```

**Where document-structure knowledge lives today.** It is duplicated across seven modules:
- `sources.py`: `mentions`, `tokens`.
- `grounding.py`: `_related`, `relationship_anchors`.
- `coverage.py`: `labelled_by`, `header_labelled`, `_relational`, and `_named_as` masking.
- `near_miss.py`: `_section_members`, `_header_evidence`, `_section_evidence`, `labelled_evidence`.
- `analysis.py`: `_labelled_segments`.
- `mapping.py`: `_lexical_relationship` and `_generic_intermediates`.
- `adjudication.py` / `verification.py`: `with_ancestors`.

All of it is used to judge, steer or contest the AI's output. None of it produces evidence.

---

## 2. Architectural diagnosis

### Verdict on the hypothesis

**Right in direction, wrong about the cause, and incomplete.**

**Where it is right.** The AI repeatedly rediscovers structure that OnyxJar already holds:
- `Segment.cells` and `Segment.header` exist, but the AI sees only `"Pool A | New Zealand v Fiji | Eden Park"`.
- `near_miss._header_evidence` already establishes that a Match-column cell exists in the row. That is used only to contest a probe verdict.
- In 24063e61 the probe was shown `S1#t3.r1` for "Pool A has_match ?" and answered "No match entities for Pool A are explicitly named".

**Where it would be wrong if read literally.** Structure alone does not give meaning for the hard cases:
- the header-less Teams table: pool membership or tournament participation?
- "Primary use: Pool matches", a generic intermediate;
- "Pool A winner v Pool B runner-up", a placeholder;
- "Final", a stage or a match?
- "Pool A" vs "Pool Stage".

These are semantic. Adjudication already handles some of them consistently (`refers_to_intermediate`).

**Where it is incomplete.** The core defect is the **granularity and shape of the AI's output contract**:
1. **Per-instance free-text claims.** A table's meaning lives in its column schema, yet the AI emits one assertion per row per relationship, with invented predicate wording. Each run invented different wording ("is listed under", "hosts", "is used for", "primary use is"), and each wording became its own `predicate_mapping` question. The semantic step happens twice and N times over.
2. **Segment-level, lexically noisy coverage.** One dismissal is required per segment (36 in 24063e61), and false relevance ("Final" inside "quarter-final") drives correction re-asks.
3. **Search driven by requirements.** Probes are posed per rule per entity (18–22 per round) over overlapping packs of the same small document.
4. **Verification has no specific question.** It gets a 58k–206k historical ledger and is asked to reconstruct causality. It approved zero-change runs seven times.

### What is fundamentally wrong / merely inefficient / sound

**Fundamentally wrong:**
- the per-instance claim contract plus per-segment dismissals for structured content;
- no canonical structural representation;
- Verification scoped to "everything" rather than to causes.

**Merely inefficient:**
- the whole catalogue is resent on every extraction call;
- 16k chars of prompt and schema per call, with almost no caching;
- probe packs overlap;
- ledger restatement.

**Sound, retained:**
- the EvidenceGraph (I1);
- provenance and ingress;
- clustering, mapping options, identity, ESC and cascades, observation conflicts;
- the compiler, TracePolicy, resolution, staging, ChangeSet v3;
- the bounded engine;
- Adjudication with its Questions and Pins;
- tracing and replay;
- partial outcomes;
- the completed `not_stated` contest safeguard, as legacy behaviour.

### Why prompt fixes kept uncovering the next failure

Each fix tightened one shape of per-instance claim. But the failure surface is rows × relationships × wordings × citation shapes, so every run had fresh ways to fail.

The correction, probe-contest and verification layers mostly **compensate for the weak evidence representation**. The one clear exception: the `not_stated` contest also established a real *semantic* rule. A negative answer is not trustworthy while structurally labelled evidence exists. The new architecture must keep that rule and enforce it structurally (§3.5, Phase 4).

---

## 3. Target architecture

```
Document bytes
 └─[OJ] Readers + segmentation (UNCHANGED; segment ids frozen)
 └─[OJ] DOCUMENT EVIDENCE MODEL (DEM) — structural only (invariant 1)
        Tables{table_id, header cells?, Columns{col_id, label_text}, Rows{row_id (=segment id), Cells{cell_id, col_id, text}}}
        Sections{heading segment, level, member ids, parent}; Items; Prose blocks; exact text + offsets
        Textual facts: normalised string occurrences, recurring in-cell separators per column (" v ", ","), repeated values
        Structural relations: cell∈column, cell∈row, row∈table, item∈section, section⊂section, caption→table
        Structural signatures: per table/section (arity, header text, per-column separator pattern, cell-emptiness profile)
        Queries (single module): leads(names, labels), related, section_members, header_for, column_cells,
                                 structurally_conforms(row, signature)        <- purely structural
 └─[AI] READING — schema-level semantic interpretation of structured elements, in BOUNDED BATCHES (invariant 2)
 └─[OJ] EXPANSION — reading_conforms(row, reading) [Reading/Expansion concern, not DEM] gates every row;
        conforming rows -> EvidenceGraph claims (origin=reading, basis_refs); nonconforming -> ANOMALIES (invariant 5)
 └─[AI] PROSE EXTRACTION — today's Extraction over prose_eligible(dem, readings) only (§3.2a): DEM-classified prose
        not owned by a Section Reading, plus tables explicitly judged not_a_table; never structured content otherwise
 └─[AI] ADJUDICATION — unchanged machinery; + question kinds `reading_slot`, `row_exception` (grouped by anomaly signature)
 └─[OJ] ANALYSIS — unchanged core (normalise, map, identity, ESC, values, conflicts); Reading-derived claims BYPASS mapping:
        their type:/map: decisions come straight from the Reading overlay (basis reading), legality-checked only
 └─[OJ] GAP TRIAGE — per unsatisfied requirement: structural lead / prose lead / no evidence (§3.6)
 └─[OJ] COMPILE / TracePolicy / resolution / staging (unchanged)
 └─[AI] REVIEW (Verification v2) — bounded CAUSAL dossier (§3.7)
 └─[OJ] commit_proposal (unchanged)
```

### 3.1 DEM boundary (invariant 1: structural, never semantic)

**The DEM may say** that `S1#t3.r1` has the cells `c1 (column label "Stage") = "Pool A"`, `c2 ("Match") = "New Zealand v Fiji"` and `c3 ("Venue") = "Eden Park"`. It may also say that column c2 has the recurring separator `" v "` in 6 of 6 rows, and that "Eden Park" also occurs in `S1#t2.r1` and `S1#10`.

**The DEM must never say** that "New Zealand v Fiji" is a Match, that Eden Park is a Venue, or that Pool A has a match. It also never offers a catalogue type or relationship.

Lexical similarity between a header label and a catalogue name is computed *outside* the DEM. It lives in the Reading option builder, and only to **order the options offered**. It never selects an option.

**Deterministic ids.** These must be stable for testing.
- Row, table, heading and item ids are today's segment ids (`S1#t3.r1`, `S1#t3`, `S1#15`), unchanged.
- `column_id = <table_segment_id>.c<k>`, e.g. `S1#t3.c2`.
- `cell_id = <row_segment_id>.c<k>`, e.g. `S1#t3.r1.c2`.
- `k` is the 1-based position of the cell in `Segment.cells`, which is the same position as in `Segment.header`.
- `section_id` is the heading segment's id.
- **Property:** given the same segmented source, the same row or cell always gets the same id across runs. That keeps the chain ProposalChange → claim → Reading → cell → segment reproducible.

**Conformance has two halves:**
- **`structurally_conforms(row, signature)`** is a DEM query and purely structural. It checks arity and alignment with the column map, header-repeat and caption/subtotal shape, cell emptiness, and the separator pattern of each column.
- **`reading_conforms(row, reading)`** is **not** a DEM function. It lives in `reconcile/readings.py` and combines exactly two inputs:
  - **(a)** the deterministic structural facts from the DEM: arity, emptiness, separator shape, part count;
  - **(b)** the semantic exceptions **declared by the Reading** (`exceptions`).

  It checks only the *consequences* of the Reading's decisions. For example, a cell that a decided entity role needs is non-empty, and a split slot's part count matches the slot.

  It **never interprets raw strings itself**. It does no cross-column text comparison, no placeholder or keyword detection, and no surface-overlap test. Surface-string overlap alone is never an anomaly; semantic interpretation belongs only to the Reading.

  Only rows that pass both halves are expanded.

**Tested enforcement (Phase 1):**
- **Import boundary:** `ai/services/document/` may not import `ai.services.semantic`, `reconcile.mapping`, the catalogue, the index or `evidence_graph`. This mirrors the existing `test_evidence_graph` boundary test.
- **Schema check:** no DEM type has a field whose name or meaning is ontological (`type`, `type_key`, `type_hint`, `relationship`, `kind_of_entity` …). A field allow-list test enforces this.
- **Catalogue independence:** the same document built against two different catalogues gives identical DEM digests.
- **Deterministic ids, and structural predicates and conformance** (`structurally_conforms`, `structured_source_segments`), tested without any Reading present.
- **No claims from structure** (Phase 2, when `expand()` exists): `expand(dem, readings=[])` returns an empty EvidenceGraph. No path from the DEM into the EvidenceGraph exists without a Reading.

### 3.2 Reading: schema-level by construction (invariant 2)

A Reading interprets **one table schema or one section** once. Deterministic Expansion applies it to every conforming row or item.

**Example.** For `Stage | Match | Venue` (t3), the Reading has these slots:
- `role(c1)` = entity of an offered type option, e.g. `stage`, specific;
- `role(c2)` = entity `match`, specific;
- `role(c3)` = entity `venue`;
- `split(c2, " v ")` = the parts are `team` entities, related to the c2 entity by `has_team` (as_stated);
- `relation(c1→c2)` = `has_match`, as_stated;
- `relation(c2→c3)` = `played_at`, as_stated.

Each slot is chosen from OnyxJar-offered options (computed with `mapping.direct_options` and the catalogue), plus `none` and `undecidable`.

**Basis rule.** Every decided slot needs a sufficient structural basis, cited by DEM id with verbatim excerpts. Normally that is the relevant header or section context plus representative row cells. Where no data rows exist, the header or section context alone may be enough. The system never fabricates sample evidence.

| Structure | Sufficient basis |
|---|---|
| Header + data rows | Relevant header cell(s) plus sample cells of the interpreted column(s) |
| Headerless + data rows | Section or ancestor heading context plus sample row cells. Example: t1 cites the "Teams" heading `S1#5` and cells of `S1#t1.r1` / `S1#t1.r2`. |
| Header-only (empty table) | The header cell(s), and section context when present. The slot may be decided, but expansion yields no instances. |
| Neither a useful header nor rows | No sufficient basis for a role. The slot stays `undecidable`, or the Reading is `not_a_table` (`unusable_recovery`) with the structure as its basis. |

A `section_relation` slot cites the section heading, the ancestor heading that names the entity and, where they exist, member samples.

A decided slot without a sufficient basis is a shape error: re-asked once, then `undecidable`.

**Candidate recall (reachability, not "the whole catalogue in every prompt").**

The invariant: deterministic candidate generation may rank, prioritise and slice candidates, but it must never make an ontology-compatible interpretation **unreachable** because of a lexical mismatch.

The mechanism is bounded:
- **Ranked shortlist.** Each slot is offered a shortlist ranked by lexical similarity to the header or heading, ontology compatibility with sibling slots (rules, types, orientation legality via `mapping.direct_options`), intent context, section context and connected catalogue neighbourhood.
- **Escape valve, central to the design.** Every payload states that the catalogue may contain more than is shown, and lists the slice's key index when it fits. The response may name **any catalogue key outside the slice**. That key is validated deterministically against the full catalogue and accepted when ontology-compatible.
- **Response schema.** For the escape valve to be real, every catalogue reference in `ReadingResult` (ObjectType key, RelationshipType key, attribute key) is an **opaque string**, not a JSON-schema enum tied to the shortlist. Orientation and the reserved options `none` / `undecidable` stay small fixed enums. The shortlist is advisory input, not the response's closed universe. Validation runs against the full catalogue after parsing: a key that is valid and ontology-compatible is accepted; an unknown or illegal key is a shape error (one re-ask, then `undecidable`).
- **Hard exclusion only on ontology grounds.** An option may be dropped only for ontology incompatibility (an inactive type, an illegal rule or orientation), never for lexical distance.
- **Small catalogues** (such as the flyer's) are shown whole. That is an optimisation, not the guarantee.

Correctness never depends on lexical similarity producing the candidate.

**Schema sharing.** t4 has the same header signature as t3. It gets its own Reading id, but the Reading stage may propose "same as t3". That is still validated per table against t4's own signature and conformance.

**Bounded batches.** Reading takes bounded batches of structured elements. Each batch is limited by a size budget (header, column ids, sample rows and section outlines), never by the number of rows. AI cost scales with the number of schemas, never with the number of rows.

**Scaling invariants (Phase 2 acceptance criteria):**
- A 10× row increase with the same schemas gives the **same number of Reading calls**.
- The same schemas give the **same number of Reading slots**.
- Expansion grows linearly with rows, and is deterministic.
- More distinct schemas may legitimately need more Reading batches and calls.

The flyer's 3–5 total calls is a performance objective, not an invariant.

### 3.2a What a Reading owns (explicit, element-level, non-overlapping)

**Interpretation scopes.** Every DEM element belongs to at most one scope, and each scope has at most one *active* owner (a Reading with status `validated`).

| Scope | Elements | Owner kind |
|---|---|---|
| `table_schema` | table, columns, cells, rows | Table Reading only |
| `heading_entity` | a heading's own text read as naming an entity (the title S1#1 as a Tournament) | Section Reading of that heading |
| `section_relation` | the relationship between a section's members and the entity its ancestor heading names (Teams → tournament) | Section Reading of that section |
| `section_items` | list items read as the section's members (only items, never table cells) | Section Reading of that section |

**Rules:**
- A **Table Reading** owns the `table_schema` scope of its table: the table, the columns it slots, and the cells of those columns.
- A **Section Reading** owns only its heading, its `section_relation` and its `section_items` scopes. It never owns table cells or descendant text blocks, even when a table sits inside the section.
- **Shared structural context without competing owners.** When a section's members live in a table, the Section Reading's `section_relation` slot *references* the Table Reading's output, e.g. `members = entities expanded by rd:S1#t1 from columns c2..c5`. That is a read-only reference, not ownership.
  - Expansion of the relation slot takes its member instances from the referenced Table Reading.
  - Each expanded `has_team_2` claim therefore has both Readings as causal inputs.
  - Cells are interpreted only by the Table Reading. Correcting the table re-expands the relation instances too, because they depend on it.
- **No ambiguous overlap.** Validation rejects a Reading that claims an element already in another active Reading's scope. If two proposals compete for one scope (e.g. two candidate Table Readings, or a batch proposing contradictory roles), neither is expanded. The conflict becomes a dispute and a Reading-level question, and the answer decides which one becomes authoritative.

**Prose eligibility is decided by deterministic DEM classification, not by the absence of a Reading.**

The DEM classifies every segment, deterministically:

| Class | Segments |
|---|---|
| `structured` | table and table-row segments of a DEM table |
| `prose` | text blocks and list items |
| `context` | headings: citable context, never extraction targets in their own right |

This is `dem.structured_source_segments()`, a DEM query with no semantics in it.

The prose-extraction boundary is computed by one deterministic function:

```
prose_eligible(dem, readings) =
      (prose segments  −  owned_source_segments(readings))            # list items a Section Reading owns as section_items
    ∪ (structured segments of tables whose Reading status is not_a_table)
```

with headings passed as citable context only.

**No structured shortcut.** A structured segment whose Reading is pending, rejected, superseded or unresolved is **not** prose-eligible. Such a segment:
- stays `unread` in coverage;
- is triaged through `reading_slot` questions or a re-read (§3.6);
- leaves its requirements `uninvestigated` / `undecidable`, never prose claims.

Once content is deterministically recognised as structured, there is no path from it to semantic claims except through a Reading. Only an explicit `not_a_table` decision, or the DEM classifying the content as prose in the first place, makes it prose-eligible.

**`not_a_table` cannot become an escape hatch:**
- It requires an allowed reason and a structural basis (§3.3). Without them it is a shape error: re-asked once, then the Reading stays unresolved, and is **not** prose-eligible.
- **Deterministic dispute:** a `not_a_table` declared for a table that `structurally_conforms` well (a header present, plus at least two aligned rows with consistent arity) is a dispute in the review dossier (§3.7).
- Any prose claim taken from a `not_a_table` region carries that provenance, so a review objection to the `not_a_table` decision retracts those claims and re-opens the Reading.

**Projection to source segments.** Ownership stays fine-grained in DEM ids (`owns`). A single deterministic function, `owned_source_segments(readings) -> set[segment_id]`, converts it into source segment ids. `prose_eligible` uses that projection, and prose extraction never reasons about cells.
- **Validated Table Reading:** excludes the table segment and every row segment of that table. Rows that are anomalous for some slot stay excluded from prose extraction, because they go to `row_exception` (§3.5), not to prose.
  - Example: a Table Reading owning the cells of `S1#t3.r1` excludes `S1#t3.r1`.
  - Columns with no slot are not owned. They show up as `unread` columns in coverage and are handled by triage (§3.6) through a `reading_slot` question, never through prose extraction.
- **Section Reading:** excludes its heading segment (when it owns `heading_entity`) and the list-item segments it owns as `section_items`. Nothing else.
- **Reading with status `not_a_table`:** owns nothing. Its table's segments become prose-eligible through the `not_a_table` term of `prose_eligible`.
- **Reading with status `rejected`, `superseded` or `proposed`:** owns nothing, but its structured segments do **not** become prose-eligible (no structured shortcut).
- **Containment alone never excludes a prose segment.**

**Tests (Phase 2):**
- `owned_source_segments` with a t3 Table Reading returns exactly `{S1#t3, S1#t3.r1..r4}`.
- A Section Reading of "Teams" excludes `S1#5` (only if it owns `heading_entity`) and none of `S1#t1*`. A prose paragraph under "Teams" stays in the prose payload.
- A `not_a_table` t1 returns its rows to prose.
- **No structured shortcut:** with t3's Reading rejected, pending or superseded (and with no Reading at all), no `S1#t3*` segment appears in any prose-extraction payload, and no prose claim cites one. t3 is reported `unread` and triaged.
- `structured_source_segments` is catalogue-independent (DEM suite) and covers every table and row segment of the flyer.
- Two Readings claiming the cells of t1 fail validation, or produce a dispute, and nothing is expanded from t1 until it is resolved.

### 3.3 Reading identity and lifecycle

```
Reading {
  reading_id      "rd:<dem_element_id>"                 stable across revisions and re-runs of the same DEM
  revision        int (1..)                             bumped by every semantic correction
  element         {kind: table|section|list, dem_id, dem_digest, signature}
  owns            [DEM ids explicitly interpreted: column ids, cell ids, item ids, the heading]   (§3.2a)
  slots: [Slot {
      slot_id     "rd:S1#t3:relation:c1>c2"             stable
      kind        role | split | relation | section_relation | specificity
      options     [option ids offered by OnyxJar, + none, undecidable]
      selected    option id | null
      state       decided | undecidable | pending | rejected
      set_by      reading | adjudicated | verifier       (who decided this revision)
      basis       [DEM refs: header cell ids (if a header exists) OR section/ancestor heading ids (headerless),
                   + sample cell ids] + verbatim excerpts   -- required for every decided slot (§3.2 basis rule)
  }]
  status          proposed | validated | not_a_table | superseded | rejected
                  (proposed -> validated -> (revision -> validated)*; proposed -> not_a_table; any -> superseded/rejected)
                  not_a_table = CONSTRAINED Reading-level classification: valid only when the recovered structure itself
                  is unsuitable for table interpretation -- reason in {layout_grid, form, decorative_alignment,
                  unusable_recovery}, with a required structural basis (cited DEM ids showing why). It is NOT an
                  alternative to `none`/`undecidable` for semantic roles of a valid table. Owns nothing, expands
                  nothing; segments become prose-eligible; always listed in the review dossier as a disputable decision.
                  Slot options stay: catalogue options | none | undecidable  (none = this role/relationship does not apply)
  references      [other reading ids whose output a slot consumes read-only, e.g. section_relation -> table]   (§3.2a)
  exceptions      [{row_ids|part refs, slot_id, kind: placeholder|generic|role_conflict|ontology_contradiction|other,
                    state: decided|undecidable, basis}]                                                    (§3.5)
  history         [{revision, slot changes, set_by, reason}]
}
```

**Ledger.**
- Every decided slot is a `kind: claim` decision, `read:<slot_id>@<revision>`, with its excerpts. **This is the AI semantic claim.**
- Each expanded claim is registered as `kind: structural`, with inputs `[read:<slot_id>@<rev>…, dem:<cell_id>…]`.

**Expanded claims.** Ids are deterministic, `x:<reading_id>:<row_id>:<slot>`, so re-expansion is idempotent. Each carries `origin = "reading"` and **`basis_refs`**: the complete, non-empty, sorted list of `"<reading_id>@<revision>"` for **every** Reading whose decision is needed to reproduce the claim.
- Most claims have one entry.
- A `section_relation` instance (tournament `has_team_2` team) lists both the Section Reading and the referenced Table Reading that produced the member entity.
- There is no "primary" basis that can hide a dependency. The claim id's `<reading_id>` names the Reading that emitted it, for identity only.
- The ledger inputs mirror `basis_refs`: one `read:<slot>@<rev>` per contributing slot, plus the DEM cells.
- **Invalidation:** a revision bump of *any* Reading in a claim's `basis_refs` supersedes that claim and triggers re-expansion of every Reading that emitted claims depending on it.

**Reading-derived claims are already canonically mapped and bypass ordinary mapping.**
- A Reading slot that holds a selected ontology option is the mapping decision. Expansion writes the EvidenceGraph item: entity name = the cell or part text, assertion endpoints = the expanded entities. The selected catalogue identities (ObjectType key, RelationshipType key, orientation) go into a **Reading mapping overlay** in `reconcile/readings.py`, keyed by claim id. The EvidenceGraph module stays catalogue-free (I1).
- The assertion's `predicate` is a display label only, the selected relationship's name. It is never interpreted.
- In analysis, Reading-origin items skip `map_entity_types` / `map_assertions` (no lexical, hint or option computation, no `predicate_mapping` / `indirect_classification` questions). Instead they receive `type:` / `map:` decisions with basis `reading` and inputs `[read:<slot>@<rev>]` directly from the overlay.
- Deterministic **legality** checks still apply: the rule exists, the type is active, the orientation is legal. They are governance, not interpretation. A failure is a Reading shape error, not a mapping question.
- `mapping.py` takes part only *before* expansion, in candidate generation (`direct_options`). It is never a second semantic step after expansion.

**Causal chain** (queryable, tested): ProposalChange → ChangeTrace entry → expanded evidence claim → `read:` slot decision → DEM cells and structure.

**Re-expansion on correction.**
- A revision bump marks every claim whose `basis_refs` contains the old revision superseded. This is an overlay, like `rs.retracted`, so the graph stays append-only (I1).
- Expansion then re-runs for that Reading only.
- Analysis recomputes as today.

One correction therefore rebuilds all derived row evidence (§3.8).

### 3.4 Distinct negative states (invariant 6)

Each unsatisfied requirement, and each investigated proposition, carries exactly one of these states. They are never merged into a generic "blocked".

| State | Meaning | Example (flyer) | Allowed next step |
|---|---|---|---|
| `undecidable` | Structure exists, but its semantic interpretation cannot safely be decided (a Reading slot or question answered `undecidable`) | Is "Pool A winner v Pool B runner-up" a match whose teams are those parts? | Never probed as an evidence gap; a reviewer or future human answer may decide it; reported as "interpretation undecided" |
| `insufficient_evidence` | The interpretation is decided and relevant evidence exists, but it does not meet the ontology requirement (too few distinct identified counterparts, or only generic or unidentified ones) | QF matches: decided as matches, but 0 of 2 identified teams → `has_team` min 2 unmet | No probe (evidence was found); reported with evidenced/minimum counts |
| `not_stated` | The proposition was explicitly investigated over complete coverage of its relevant DEM elements (decided Readings, read prose) and the source does not state it | McLean Park `played_at` some match: both fixture tables read, no row names it | Terminal; reported as not stated |
| (deferred) `unadjudicated` / `uninvestigated` | Budget or ordering prevented the decision or investigation | (existing `open:` basis `budget`) | Kept as today; never shown as one of the three above |

**Representation.**
- A derived `Requirement.state` field, computed in analysis from `pending_decision`, `evidenced`, `viable_count`, coverage completeness and probe outcomes.
- It is surfaced in `blocked_targets`, the findings and the review dossier.

**A Reading `none` is not an absence-of-evidence result.**
- `none` is a *semantic decision*: this structural element does not carry that role or relationship. For example, "the Primary use column is not a relationship to a Match".
- `not_stated` is a *result about a proposition*, reached after the relevant source material has been interpreted.
- They are never interchangeable. A slot decided `none` (an "ignored" element) **can never directly produce `not_stated`**.
- If a requirement's only structural leads lie in elements a Reading decided `none` for that role, the state is not `not_stated`. Triage raises a challenge to that `none` decision (§3.6), and the review sees it as a dispute (§3.7).
- Only after a `none` has been reconsidered and upheld with that requirement in view may the proposition become `not_stated`, over the remaining coverage.

**Unresolved anomalies block terminal negatives.**
- An unresolved anomaly relevant to a requirement prevents any terminal negative state (`not_stated` or `insufficient_evidence`). A row or slot excluded by `reading_conforms`, whose row is a structural lead for that requirement, is such an anomaly.
- The requirement is routed through the grouped `row_exception` / Reading decision path first.
- What happens after the anomaly is resolved:
  - **Corrected** (the answer gives the row a valid interpretation, or a Reading revision changes the slot): deterministic re-expansion, then re-evaluation.
  - **Upheld** (the exclusion stands, e.g. "these placeholder parts are not identified teams"): the requirement proceeds to deterministic evaluation over the remaining evidence. For the QF rows this yields `insufficient_evidence` (matches exist, 0 of 2 identified teams).
  - **Answered `undecidable`:** the requirement state is `undecidable`.
  - **Not reached** (budget or ordering): `unadjudicated` / `uninvestigated`, never a false negative.

**Rule carried over from the legacy contest.** `not_stated` is only recordable when no structural lead for the proposition sits in an unread, undecided, or `none`-decided (not yet reconsidered) element. If such a lead exists, the state is `undecidable`, or a Reading question is raised (Gap Triage, §3.6).

In readings mode this is enforced *before* any probe, rather than by contesting a probe afterwards. A prose-probe `not_stated` that coexists with a structural lead becomes a deterministic dispute for the review (§3.7).

### 3.5 Reading application safety (invariant 5)

Expansion runs `structurally_conforms(row, signature)` (DEM) and then `reading_conforms(row, reading)` (Reading/Expansion) on every row and item. A row that fails either check is **excluded from expansion** for the affected slots, and recorded as an anomaly with a typed reason and the check that failed:

| Anomaly | Detected by | Handling |
|---|---|---|
| Arity or alignment mismatch (merged or missing cells) | `structurally_conforms` | Excluded; `row_exception` question |
| Repeated header row, caption or subtotal row (one spanning cell, or text equal to the header) | `structurally_conforms` | Deterministic skip, recorded (no AI) |
| Empty cell in a column whose decided role needs a value | `reading_conforms` | Excluded for the slots that need that cell; other slots still expand |
| Split mismatch (a split-slot column without the separator, or with the wrong number of parts) | `structurally_conforms` (pattern) plus `reading_conforms` (part count the slot requires) | Excluded for the split slot; question |
| **Reading-declared semantic exception**: the Reading identifies, for specific rows or parts, a role conflict, a placeholder or generic reference, an ontology contradiction or another explicit incompatibility. Example: "`Pool A winner`, `Pool B runner-up` are placeholder references, not identified Teams". Declared in the Reading's `exceptions` with a basis. | The Reading (semantic), applied by `reading_conforms` | Decided exception → excluded for that slot (resolved, upheld). Exception marked `undecidable` → grouped `row_exception` question (unresolved) |
| The **same DEM occurrence** (one cell or part), or the same semantic entity candidate within an **overlapping interpretation scope** (e.g. a Section Reading's relation slot consuming a Table Reading's column), receives incompatible Reading assignments. Surface-string equality across different contexts ("New Zealand" in t1 and in t3) is **not** a conflict: that is ordinary text reuse, left to clustering and identity. | Reading validation (not `reading_conforms`): compares the Readings' *decisions* keyed by DEM occurrence ids and scope references, never by text | Dispute, then a Reading-level question |

- **Surface-text overlap is never an anomaly by itself.** The same string in two roles (`Category = New Zealand`, `Team = New Zealand`) is legitimate.
  - Semantic exceptions come only from the Reading.
  - Deterministic checks are limited to structure (arity, header repeat, separator shape, emptiness against decided roles) and to incompatible assignments to the *same* DEM occurrence or overlapping scope.
- **Which rows the Reading sees.** The Reading sees every row when the table is small. At scale it sees samples **plus every structural outlier row**: rows whose cell shape deviates from the column's dominant shape (token-count, separator or emptiness pattern). That is a purely statistical, structural selection. So rows needing a semantic exception are put in front of the Reading. A row that is not shown is expanded only if it is structurally typical.
- **Grouping.** `row_exception` questions are grouped by (Reading, anomaly signature). The 2 QF rows become **one** question, not two, which keeps correction at schema leverage.
- **Tests (Phase 2):** a seeded malformed row, a header repeat, a missing separator and the QF placeholder rows must not produce expanded claims for the affected slots, and must each appear as an anomaly or question.
- **`reading_conforms` is not a second interpreter.** A test gives it the QF rows under a Reading that declares **no** exceptions, and asserts the rows are expanded. Deterministic code must not rediscover the placeholders from their text. The exclusion happens only when the Reading declares the exception.
- **Boundary tests:**
  - `structurally_conforms` is tested in the DEM suite with no Reading present.
  - `reading_conforms` is tested in the Reading suite.
  - The DEM import-boundary test also guarantees that `reading_conforms` cannot live in `ai/services/document/`.

### 3.6 Gap triage (deterministic routing)

For each unsatisfied requirement whose state is not yet decided, `document.leads()` (consolidated from `labelled_evidence`, `_section_evidence` and `_section_members`) classifies it. The checks run in this order:
0. **A structural lead in a row with an unresolved relevant anomaly.** Route to the grouped `row_exception` question first. No terminal negative state is allowed until it is resolved (§3.4). This takes precedence over 1–4.
1. **A structural lead in an element whose relevant slot is decided with a role (not `none`), and with no unresolved relevant anomaly.** Already expanded, so the state is `insufficient_evidence`, or `not_stated` if no expanded instance names the counterpart. Decided deterministically.
2. **A structural lead in an unread or undecided element, or in one whose relevant slot is `none`.** This raises a `reading_slot` question for that element: one question per element, not per requirement. For a `none` slot the question is a **challenge**: it states the requirement and the lead, and asks whether the `none` decision stands. A `none` is never turned into `not_stated` without that reconsideration (§3.4).
3. **Only prose leads.** A targeted Gap Probe (today's machinery, prose-only packs).
4. **No lead, with complete coverage.** `not_stated` with no AI call.

### 3.7 Verification v2: a causal review

The reviewer answers two questions:
- **(Q1) Are the decisions that *caused* the proposed changes sound?**
- **(Q2) Are the decisions that *prevented* other changes justified?**

**Dossier contents.** Bounded, built by `review_dossier()`, and never containing the full ledger:
1. **The causes of changes:** for each ProposalChange group, the causal chain back to its `read:` slots, adjudicated answers or prose claims, with 2–3 instance samples per Reading and all its anomalies.
2. **The causes of blocks:** for each blocked root (`Analysis.cascade` cause), its negative state (§3.4), the upstream decisions it rests on, and its **DEM leads**.
3. **Deterministic disputes**, computed rather than inferred by the model:
   - a lead into an undecided element, or into one whose relevant slot is `none` (shown as a challenge to that semantic decision, never as "not stated");
   - every `not_a_table` decision with its reason and basis, flagged when the table structurally conforms well;
   - a `not_stated` coexisting with a structural lead;
   - Readings that conflict;
   - repeated anomaly signatures;
   - target-relevant prose left unread.
4. **`none`-decided ("ignored") structural elements**, each with its Reading basis and labelled as a semantic decision; and **unread target-relevant prose**.

**Objections** target decision ids:
- `read:` slots: re-pin plus re-expansion, the high-leverage path;
- `adj:` and the other question pins: as today;
- prose evidence ids: retract;
- action ids: exclude.

`VerificationStage.route`, `_answer_issue` and the commit path are kept. `verification_ledger` and `_restated` are not used in readings mode.

**Bound.** Size is O(decisions causing changes + blocked roots + disputes), with instance samples capped. It does not grow with rows or with the number of ledger families.

### 3.8 Correction is higher-leverage at Reading level (a design property)

- **Semantic correction goes to the Reading.** A Reading-level objection, adjudication or row-exception answer changes **one slot**, which re-expands every affected row. No design path issues per-row semantic correction for rows that conform to a Reading.
- **Per-row AI attention** exists only for anomaly groups, and is grouped by signature.
- **Shape errors in a Reading** (an unknown column id, an option that was not offered, a missing basis) are validated locally and get at most one re-ask.
- **Prose claims** keep today's item-level correction.

### 3.9 I2, made precise (invariant 3)

- OnyxJar never manufactures a semantic claim from structure alone.
- **A Reading slot is an AI semantic decision**, with a verbatim basis.
- **Expansion is a deterministic structural consequence** of that decision applied to DEM cells. It is stored in the existing EvidenceGraph, with `origin = reading` and `basis_refs` = every contributing `reading_id@revision`, and registered as `kind: structural`, with every contributing slot decision and the DEM cells as inputs.
- `ledger.rests_on_claim` and `trace_policy.check_trace` resolve an expanded claim to its `read:` claim decision. A `reading`-origin item with empty or unresolvable `basis_refs`, or whose ledger inputs omit a Reading in `basis_refs`, is an I2 violation.
- **The gap this closes.** Today `_register_claims` registers *any* graph item as a `kind: claim` root regardless of origin. Without this change, a deterministically produced item would make I2 vacuous. Tests cover it (Phase 2).

### 3.10 The design questions, answered

1. **What is the canonical representation of document structure?** The DEM (§3.1).
2. **What is the canonical representation of semantic assertions?** Reading slots (schema-level), plus EvidenceGraph claims: expanded claims from Readings and extracted claims from prose.
3. **How are provenance and citations represented?** Expanded claims cite `segment_id` = the row, `locator` = the cell id, `excerpt` = the cell text, plus the header cell. `EvidenceReference` stays as it is: source = file name, locator = segment id, optionally with a cell suffix; note = excerpt.
4. **How does the AI consume evidence?** Readings see DEM elements: header, typed column ids and sample rows, all rows when small or a stratified sample plus anomalies when large, and section outlines. Prose extraction sees prose segments only.
5. **How does the AI report uncertainty?** Options plus `none` / `undecidable` per slot; `row_exception` and other typed Questions (I4); the distinct negative states (§3.4).
6. **Which facts are never allowed to depend on an LLM?**
   - table, row, cell and column membership;
   - header text;
   - section containment and order;
   - exact text;
   - string occurrences;
   - separator patterns;
   - L1/L2 citation validity;
   - row conformance;
   - structural leads;
   - coverage of structured elements.
7. **Where does correction happen?** Reading slots (semantic, high leverage); anomaly groups; prose items; Reading shape (local).
8. **Where does ambiguity resolution happen?** In Adjudication (unchanged machinery, with the new question kinds), or by the reviewer through objections on decision ids.
9. **Where does verification happen?** Deterministically for structure, conformance and governance. The AI reviews causal adequacy (L3) via the dossier.
10. **What does Verification need to see?** §3.7.
11. **How does a later stage consume results without rereading the source?** Through DEM ids, Reading slots and EvidenceGraph claims. Source text is shown only where a decision is being made about it.

### 3.11 Classification of responsibilities (A / B / C)

**A: deterministic document and evidence processing:**
- tables, rows, cells and column labels;
- sections and containment;
- exact text and provenance;
- L1/L2 grounding;
- string occurrences of names;
- duplicate handling by exact normalised equality;
- in-column separator patterns;
- row conformance;
- structural leads.

**B: semantic interpretation:**
- column role and type;
- composite-part meaning;
- column-pair relationship and orientation;
- section-to-ancestor relationship (Teams under the tournament title);
- generic references ("Pool matches");
- placeholders (QF participants);
- the Final as stage vs match;
- "Pool Stage" vs "Pool A";
- prose relationships;
- non-identical coreference.

**C: deterministic reconciliation and governance:**
- requirement satisfaction and the negative-state classification;
- cardinality, closure and cascades;
- conflicts;
- gap triage;
- compile, TracePolicy, resolution, staging and commit.

---

## 4. Reuse assessment (retained / adapted / refactored / replaced)

**Retained unchanged:**
- `assisted/services/evidence_extraction.py` (readers);
- `sources.py` segmentation and ids;
- `provenance.py`;
- `reconcile/ingress.py` (id ownership; expansion goes through `ingest` with origin `reading`);
- `reconcile/normalise.py` (clusters and observation sets);
- `reconcile/identity.py`;
- `reconcile/scope.py` (ESC, `Requirement`, cascades);
- `reconcile/compiler.py`;
- `change_set.py`, `resolution.py`, `staging.py`;
- `workflow/engine.py`, `orchestrator.py`;
- `semantic/*`;
- `stages/adjudication.py`;
- `intent_frame.py`.

**Adapted (small, additive):**
- `evidence_graph.py`: `Origin` gains `reading`; optional `basis_refs: list[str]`.
- `reconcile/ledger.py` and `trace_policy.py`: structural-consequence resolution to `read:` claims (§3.9).
- `reconcile/mapping.py`: no change to its mapping of prose claims. `direct_options` is reused for Reading candidate generation. Reading-origin items are routed around it (analysis registers their `type:` / `map:` decisions from the Reading overlay).
- `reconcile/questions.py`: the `reading_slot` and `row_exception` kinds.
- `reconcile/state.py`: `readings`, `anomalies`, `superseded`.
- `scope.Requirement`: a derived `state` (§3.4).
- `reconcile/responses.py`: `ReadingResult` and `ReviewResult`.
- `operation_definitions.py` and `stages/reconcile_steps.py`: the Reading stage, triage routing and budgets.
- `tracing.py`: the DEM digest and Readings in snapshots, plus the fixture-capture command.
- `evidence_bundle.py`: a `.document` accessor.

**Refactored:**
- `reconcile/analysis.py`, about 60% kept. `_register_claims`, `_coverage`, `_labelled_segments`, `_target_work` and `_probe_requests` become DEM coverage and triage in readings mode.
- `grounding.py`: L1/L2 kept; `_related` and `relationship_anchors` delegate to the DEM.
- `reconcile/near_miss.py`: lead computation moves to `document.queries`; prose pack building kept.
- `stages/extraction.py`: becomes prose-only in readings mode; `absorb`, `settle` and item correction kept.
- `stages/gap_probe.py`: prose-only in readings mode. The legacy contest machinery stays active in claims mode until Phase 6.
- `stages/verification.py`: `review_dossier()` in readings mode; `route()` and commit kept.

**Replaced (readings mode):**
- `reconcile/coverage.py` lexical relevance, replaced by DEM coverage.
- Most of `stages/prompts.py`: a new READING prompt, a prose-only EXTRACTION and a causal REVIEW. ADJUDICATION is kept.

**Removed (only in Phase 6):**
- table dismissals;
- segment re-asks for tables;
- `unaccounted_reask`;
- `no_anchor` / correction anchors for tables;
- `not_stated_contested` / `reprobed` / `probe_contested`;
- `verification_ledger` / `_restated`;
- the claims-mode branches.

**Survival estimate.**
- About 6.5k of the ~10k Reconcile service lines survive essentially intact.
- About 1k lines are adapted.
- About 2.4k lines of AI-facing machinery are replaced or refactored.

---

## 5. Regression matrix (observed failures → architectural owner)

| Observed failure (runs) | Root class | Owner in the new architecture | Regression test |
|---|---|---|---|
| Fixture rows dismissed as off-target (24063e61, 286357bd) | Coverage-protocol design | Readings of t3/t4 (no table dismissals); DEM coverage: "column unread" is visible and triaged | Phase 3: no `t3`/`t4` row is left unread or dismissed when Readings exist; scripted Reading that *ignores* c2 raises a dispute |
| Venue→match relationships repeatedly missed | Representation (column pair never presented) | `relation(c2→c3)` slot, expanded to every row | Phase 2: the 4 pool fixtures produce 4 `played_at` claims from one slot |
| Pool A / Pool Stage lexical confusion | Lexical relevance plus a semantic question | DEM exact string occurrences (no token-overlap relevance); Stage-column Reading decides the type; "Pool Stage" (prose) vs "Pool A" coreference stays a question, never a lexical merge | Phase 1: exact-occurrence test; Phase 0: no non-identical merge |
| Quarter-final placeholder entities | Genuine semantics | A Reading-declared `placeholder` exception on t4's split slot. If decided, it is excluded (upheld) → `insufficient_evidence`. If `undecidable`, a grouped `row_exception` question, with QF non-terminal until it is answered: corrected → re-expanded; upheld → `insufficient_evidence`; `undecidable`; deferred → `unadjudicated` | Phase 2: no Team entities expanded from "Pool A winner"; at most one grouped question. Phase 4: no terminal negative for QF while the exception is unresolved. Cross-role text reuse (a "New Zealand" fixture) creates no anomaly |
| Final: stage vs match | Genuine semantics | A prose extraction question with `undecidable` | Phase 0 oracle covers both answers; Phase 2 scripted |
| Header-less Teams table | Genuine semantics plus structure | DEM: table under the "Teams" section under the title; one Reading of t1 plus one `section_relation` slot to the title entity | Phase 2: 8 `has_team_2` claims from ≤2 slots, or `undecidable` → no team claims |
| McLean Park unsupported despite appearing | Correct governance | Triage: leads in read elements → `not_stated` for `played_at` | Phase 0: McLean Park is never compiled; Phase 4: state is `not_stated`, not `insufficient_evidence` |
| Incorrect `not_stated` outcomes (24063e61 probe on S1#t3.r1) | Representation, plus a missing structural guard | §3.4 rule: `not_stated` is impossible while a structural lead sits in an unread or undecided element | Phase 4: a scripted probe answering `not_stated` over a labelled lead becomes a dispute, never terminal |
| Verification approving an incorrect final state (all 7 runs) | Wrong verification input | Causal dossier with deterministic disputes | Phase 5 seeded-defect tests (below) |
| Invented predicates → per-wording `predicate_mapping` questions | Per-instance contract | Relationship slots from offered options; Reading-derived claims bypass ordinary mapping | Phase 2: zero `predicate_mapping` / `indirect_classification` questions for expanded assertions; `map_assertions` is never invoked on Reading-origin items |
| `self_reference` / `missing_endpoint` on "Primary use" cells | Contract defect | Reading role options for the `Primary use` column (generic reference, value, ignore); intermediates via existing `indirect` | Phase 2: no self-reference claims from t2 |

---

## 6. Migration plan

The new path runs behind a flag: `AI_RECONCILE_EVIDENCE_MODE = "claims" | "readings"`.

`claims` (the current architecture, including the completed `not_stated` contest) is the default and stays fully supported until the Phase 6 gate. Every phase leaves both modes working.

### Phase 0: Deterministic governance-core contract (no live-model behaviour change)

**Objective:** establish the governance core as a contract before introducing the DEM and Reading.

**New test file: `ai/tests/test_governance_contract.py`.** It feeds ideal semantic input (built in `rugby.py` / `support.py`) directly to `run_analysis` → compile → resolve → stage.

**Positive guarantees:**
- the reference partial outcome from §0;
- valid structural evidence supplied through ideal semantic input satisfies the intended requirement (e.g. a `support: structural` heading/item assertion satisfies `has_team_2`).

**Negative guarantees:**
- QF requirements stay blocked when their matches have no identified teams, even though related entities (venues, stages) exist and are compiled;
- McLean Park is never evidenced or compiled merely because it appears in t2, S1#10-adjacent text or elsewhere;
- self-referential, missing-endpoint and unanchored claims stay rejected at ingress and analysis;
- cardinality and rule constraints stay authoritative (e.g. a third team on a match is a `constraint_conflict`, never compiled);
- upstream blocking and cascade are correct (Eden Park ← NZ v Fiji ← New Zealand ← the tournament's `has_team_2` when the teams claim is withheld);
- **structure alone manufactures nothing:** a bundle with full segments and no claims produces zero changes, zero requirements satisfied and no I2 violations.

**Reference specs.** Write `ai/tests/fixtures/references/` specs and the `assert_reference` checker (used by the Phase 5 gate) for the flyer, `rugby_flyer.txt`, the resilience chain, and one new prose-heavy canonical document. The governance contract asserts the flyer spec against ideal semantic input.

**Fixture capture and reproducibility:**
- `ai/management/commands/capture_reconcile_fixture.py` turns a raw trace into a stripped, `request`-annotated fixture. Acceptance: it reproduces an existing fixture byte-for-byte, apart from intentionally stripped fields.
- A segment-id stability test pins every segment id and text of the flyer PDF and `rugby_flyer.txt`.

**Acceptance:**
- the contract suite passes. If it fails, the failures are filed as core defects and fixed before Phase 1;
- the existing suite is green;
- `replay_baseline.json` is unchanged.

### Phase 1: DEM (additive, consolidating; legacy behaviour unchanged)

**New:** `ai/services/document/{model.py, build.py, queries.py}`, containing:
- `DocumentModel`, `Table`, `Column`, `Cell`, `Section`, `Item`, `Occurrence`, `SeparatorPattern` and `Signature`;
- `leads`, `related`, `section_members`, `header_for`, `column_cells` and `structurally_conforms`. `reading_conforms` arrives in Phase 2 in `reconcile/readings.py`, outside the DEM.
- Deterministic column and cell ids (§3.1), with a stability test: building twice from the same source gives identical ids.

**Refactor (pure delegation, identical outputs):**
- coverage `labelled_by` / `header_labelled` / `_relational`;
- near_miss `_header_evidence` / `_section_evidence` / `_section_members` / `labelled_evidence`;
- grounding `_related` / `relationship_anchors`;
- analysis `_labelled_segments`.

**DEM invariant tests (§3.1), all purely DEM:**
- import boundary;
- structural-only schema (field allow-list, no semantic fields);
- catalogue independence;
- deterministic ids;
- the structural predicates `structurally_conforms` and `structured_source_segments`.

There are no expansion tests in this phase.

**Acceptance:**
- the full `ai` suite is green, including `test_trace_equivalence`, with `replay_baseline.json` unchanged;
- no payload or schema change in claims mode;
- the structural predicates have one implementation;
- DEM unit tests cover the flyer PDF, `rugby_flyer.txt`, docx tables, pipe tables and the header-less t1.

### Phase 2: Reading stage plus deterministic Expansion (readings mode only)

**New:**
- `stages/reading.py` (`ReadingStage`: bounded batches of structured elements, plus at most one shape re-ask per batch);
- `reconcile/readings.py` (the Reading model of §3.3 with explicit `owns`, an option builder using `mapping.direct_options`, validation against DEM ids and offered options, `expand()`, `reading_conforms()`, anomaly grouping);
- the `ReadingResult` schema and the READING prompt;
- the `reading_slot` / `row_exception` question kinds;
- `origin = reading` and `basis_refs` (plural, all contributing Readings);
- ledger and TracePolicy causal resolution (§3.9);
- a supersede-and-re-expand path on Reading revision.

**Behaviour.** Reading runs in bounded batches before Extraction. Extraction receives exactly `prose_eligible(dem, readings)` (§3.2a).

**Acceptance criteria (correctness):**
- **Schema-level:** for the flyer and for a synthetic 10×-row variant, the number of Reading calls and Reading slots is identical. Expansion claims scale linearly with the row count. A synthetic document with more distinct schemas may use more Reading batches.
- **Ownership:** a section Reading does not remove descendant prose from prose extraction (§3.2a test).
- **Deterministic ids:** column and cell ids follow §3.1. Re-running on the same source gives identical cell ids, expanded-claim ids and `basis_refs`.
- **Causal chain:** every compiled change from a table resolves change → claim → `read:` slot → DEM cells. A test walks the chain.
- **No DEM → EvidenceGraph path without a Reading:** `expand(dem, []) == empty`, and no other code path writes `reading`-origin items.
- **I2:** a `reading`-origin item with empty or unresolvable `basis_refs` fails `check_trace`; revising the referenced Table Reading supersedes and re-expands the dependent `section_relation` claims (multi-Reading invalidation test); `rests_on_claim` resolves expanded items to `read:` claims.
- **Basis:** every decided slot has a sufficient basis per §3.2. Four cases are covered:
  - header plus rows (t3);
  - headerless plus rows (t1, with the "Teams" heading plus row cells);
  - a header-only empty table (decided from the header alone; zero instances; no fabricated samples);
  - neither a useful header nor rows (a decided role is rejected as a shape error; it ends `undecidable` or `not_a_table`).
- **Escape valve is schema-real:** `ReadingResult` catalogue references are plain strings, not enums. A test supplies a shortlist without `venue`, returns `venue` for `role(c3)`, and asserts it is accepted after full-catalogue validation. An unknown key is a shape error.
- **Candidate recall:** for the flyer, Stage, Match, Venue and Team (role slots) and `has_match`, `played_at`, `has_team` and `has_team_2` (relation and section slots) are reachable. "Reachable" means shown, or nameable through the outside-slice escape valve and then accepted by full-catalogue validation. This holds with reworded headers ("Round | Fixture | Ground"), with no header (t1), and with a deliberately tiny slice size that forces the escape valve.
- **No second mapping:** for Reading-derived claims, `map:` / `type:` decisions have basis `reading` with `read:` inputs. `map_assertions` and `map_entity_types` are not called on them. Zero `predicate_mapping` / `indirect_classification` questions arise from them. An illegal selected relationship is a Reading shape error.
- **`not_a_table` constraint:** a `not_a_table` without an allowed reason or basis is rejected, and the segments stay non-prose-eligible. A `not_a_table` declared on well-conforming t3 produces a review dispute.
- **Exceptions:** QF placeholders are excluded only through a Reading exception, decided or undecidable. A synthetic `Category = New Zealand | Team = New Zealand` table produces no anomaly.
- **No structured shortcut:** the §3.2a prose-eligibility tests pass.
- **Correction leverage:** a scripted wrong slot (e.g. `relation(c2→c3)=none`), once corrected through a single objection or adjudication, re-expands every affected row in one analysis pass, with **no per-row AI call**. Superseded claims are overlaid, not deleted.
- **Application safety (§3.5):**
  - seeded malformed, header-repeat and missing-separator rows plus the QF placeholders produce no expanded claims for the affected slots;
  - every anomaly is recorded;
  - QF anomalies form one grouped question.
- **No `predicate_mapping` questions** for expanded assertions.
- **Ownership and lifecycle:**
  - the `owned_source_segments` projection tests and the no-overlap tests (§3.2a) pass;
  - a `not_a_table` Reading returns its segments to prose extraction and expands nothing.
- **Semantic quality (deterministic):** the Phase 0 reference outcome is reached in scripted readings mode.
- **Diagnostic, not a gate:** live flyer and rugby runs in both modes are compared and recorded. Live output is stochastic, so this is evidence for tuning. Formal semantic-quality and default-flip acceptance is decided by the Phase 5 gate.

**Performance objectives (not correctness gates):** on the flyer, about 3–5 calls and 35–55k chars in total.

### Phase 3: Coverage on DEM plus Reading semantics (readings mode)

**Replace:** coverage in readings mode becomes:
- each table, column or section is `read` (a validated Reading), `ignored` (a Reading slot `none` with its basis: a semantic decision, never a negative evidence result) or `unread`;
- each prose segment is `claimed` or `unread`;
- no per-segment dismissals for structured elements.

Lexical relevance is used only to prioritise prose.

**Acceptance:**
- extraction output carries no table dismissals;
- no lexical false re-asks (the "Final"/"quarter-final" case);
- an `unread` target-relevant element always appears in triage and the dossier;
- claims-mode coverage is unchanged.

### Phase 4: Gap triage (readings mode)

**New:** `reconcile/triage.py` (§3.6) and the derived `Requirement.state` (§3.4), with the distinctions enforced end to end.

**Readings mode:**
- the probe is prose-only;
- the `not_stated` structural guard is enforced before probing;
- `not_stated_contested` / re-probe machinery is **not carried into readings mode**.

**Claims mode:** keeps the completed contest safeguard unchanged.

**Acceptance:**
- no requirement whose lead is structural is ever probed;
- a scripted `not_stated` over a structural lead becomes a dispute and never terminal;
- a requirement whose only lead is in a `none`-decided column raises a challenge question, and never becomes `not_stated` directly;
- a requirement whose lead row has an unresolved relevant anomaly is never terminal. After the grouped `row_exception` answer:
  - corrected → re-expanded;
  - upheld → evaluated over the remaining evidence (QF → `insufficient_evidence`);
  - budget-deferred → `unadjudicated`;
- every blocked requirement on the flyer reports exactly one of `undecidable` / `insufficient_evidence` / `not_stated` / deferred. QF is `insufficient_evidence` (or `undecidable` if the placeholder question was answered so). McLean Park is `not_stated`;
- `test_reconcile_resilience` (the prose-like depth chain) stays green in both modes.

### Phase 5: Bounded causal Verification dossier (readings mode)

**New:** `review_dossier()` and deterministic `disputes()` (§3.7). Objections on `read:` slots are routed through re-pin and re-expansion.

**Acceptance (correctness):**

**Review seeded-defect tests**, in replay and scripted runs. Each must draw a *material*, routable objection:
- (a) a Reading that decides `none` for the Match column;
- (b) a wrong relationship orientation slot;
- (c) a `not_stated` coexisting with a structural lead.

**Undecidable-slot condition, tested twice and kept separate:**
- **Governance test:** inject a ChangeTrace or change whose causal chain rests on an `undecidable` Reading slot. `check_trace` / compile must reject it, and nothing is staged.
- **Review test:** seed the dossier with an explicit invariant-violation entry for that condition. Verification must raise a material objection, not approve.

The dossier never contains the full ledger.

**Performance objectives:** the dossier is about 25k chars or less on the flyer, and grows with decisions and disputes, not with rows (checked on the 10× synthetic).

**Default-flip gate.** The Phase 2–5 correctness criteria must hold, and **semantic quality** must pass. Quality is defined operationally as reference assertions per canonical regression document: the flyer, `rugby_flyer.txt`, the resilience depth chain, and one prose-heavy document added in Phase 0.

Each document has a checked-in **reference spec**, `ai/tests/fixtures/references/<doc>.json`, listing:
- **Required positives:** changes that must be present, or explicitly justified as `undecidable` where the spec allows it.
- **Required negatives:** items that must stay blocked, each with its required state (`insufficient_evidence` / `not_stated` / `undecidable` / allowed alternatives).
- **Forbidden changes:** false positives that must never appear.

The spec is evaluated by one checker, `assert_reference(result, spec)`, used in three settings:
- scripted readings-mode runs (CI);
- readings-mode replay captures (CI);
- the live runs (recorded per run).

**Flyer spec (excerpt):**
- 4 pool matches present;
- 8 teams present, linked to the tournament;
- Eden Park, Sky Stadium, Forsyth Barr Stadium and FMG Stadium Waikato present with their matches;
- QF → `insufficient_evidence`, or a justified `undecidable`;
- McLean Park → `not_stated`;
- Semi-finals / Final → blocked (Final: `not_stated` or a justified `undecidable` per the stage-vs-match question);
- **forbidden:** any Team created from "Pool A winner" / "Pool B runner-up", any `played_at` for McLean Park, any compiled QF match.

**The gate has three tiers, and only deterministic inputs can fail it.**

1. **Hard correctness gate (authoritative).** Every canonical document passes its reference spec in CI: scripted readings-mode runs, plus readings-mode **replay captures**, which are deterministic once captured. Forbidden changes are hard failures everywhere.
2. **Deterministic comparison (gating).** Claims mode is compared only against **replayed claims-mode baselines**. These are the captured claims-mode runs (the existing `international_flyer_*` fixtures, plus captures of the other canonical documents), with their spec results recorded once. Readings mode must pass every spec assertion that the claims-mode replay baseline passes for the same document. Because both sides are fixed replays, AI variance cannot cause a false failure.
3. **Live comparison (supporting evidence, not gating except for forbidden changes).** Run N = 5 live runs per mode per canonical document. Record each spec assertion's pass rate per mode. Thresholds:
   - any forbidden change in any live readings-mode run → gate fails (a safety property, not a statistical one);
   - readings-mode pass rate below 0.6 on a required assertion that claims mode passes at ≥ 0.8 → flagged for investigation and a recorded decision, not an automatic failure;
   - on the flyer, readings mode is expected to reach the required positives in at least 3 of 5 runs, where the claims-mode baseline is 0 of 7. Missing that is a flag that requires a written justification.

   Calls, payload chars and dossier size are recorded alongside as performance evidence.

The regression matrix (§5) maps each row to at least one spec assertion.

### Phase 6: Retire legacy claims mode (only after demonstrated equivalence or superiority)

**Delete:**
- the claims-mode branches;
- table dismissals and segment re-asks;
- `unaccounted_reask` and `no_anchor` / correction anchors for tables;
- `not_stated_contested` / `reprobed` / `probe_contested`;
- `verification_ledger` / `_restated`;
- the claims-mode captured trace fixtures (`ai/tests/fixtures/traces/international_flyer_*`) and the claims-mode `replay_baseline.json`, once their behavioural assertions have been ported.

**Port tests before deleting them (delete mechanisms, not regression knowledge).** For each legacy test, extract the behavioural assertion, re-express it against DEM and Reading, and only then delete the implementation-specific version. Concretely:

| Legacy test | Behavioural assertion to port |
|---|---|
| `test_structural_anchors` | A relationship is only accepted where structure or text actually connects its endpoints → DEM `related` / `leads` and the Reading basis |
| `test_verification_payload` | Each fact is shown once, and nothing unroutable appears → the dossier carries no duplicate and no unroutable entries |
| `test_reconcile_convergence` live regressions | Each one's outcome-level expectation becomes a readings-mode scripted or replay case |
| `test_trace_equivalence` | Re-keyed on `reading_id` / question id / requirement id against a readings-mode baseline |

**Kept permanently as canonical regression documents:**
- the source fixtures `ai/tests/fixtures/international_rugby_flyer.pdf` and `rugby_flyer.txt`, the DEM and Reading regression inputs;
- the Phase 0 governance contract.

**Regenerate:** `replay_baseline.json` from readings-mode captures (via the Phase 0 command).

**Acceptance:**
- the governance contract (Phase 0), the DEM invariants (Phase 1) and the Phase 2–5 criteria all stay green;
- every claims-mode pathway is removed, no orphaned compatibility branches remain, and each retired mechanism is deleted or replaced by its readings-mode equivalent;
- every regression-matrix row (§5) has a readings-mode test.

Line count is reported as an observation, not a gate.

**Dependencies:**
- 0 → 1 → 2.
- 3 and 4 depend on 2 and can run in parallel.
- 5 depends on 2 and benefits from 4.
- 6 depends on 5's gate.

---

## 7. Complexity comparison

Call and token figures are **performance objectives**, not correctness constraints. The architecture is not designed around the flyer.

The real goals:
- semantic quality at least as good as today;
- less repeated interpretation;
- bounded growth with document size;
- substantially less duplicated context;
- deterministic processing of repeated structure.

Let R be the number of rows/items, S the number of tables/sections, P the prose chars, Q the genuine semantic questions, and D the decisions that changes rest on.

| | Current (claims mode) | Target (readings mode) |
|---|---|---|
| AI interpretation | O(R × relationships per row) free-text claims, plus O(segments) dismissals | O(S) Reading slots, plus O(P) prose claims |
| Deterministic work | Analysis per visit | Analysis plus O(R) expansion and conformance |
| Correction | O(defective rows), ≤2 waves | O(defective Reading slots), plus O(anomaly signatures) |
| Probes | rounds × O(unsatisfied requirements) | O(requirements with prose-only leads) |
| Adjudication | O(invented predicates + intermediates) | O(Q) |
| Verification | O(full ledger): 58k–206k chars at 1× | O(D + blocked roots + disputes), samples capped |
| 5× document | 12k-char batches, up to 4; ledger about 5× | Unchanged AI cost for the same schemas; prose linear |
| 10× document | >48k chars of segments are **silently `unextracted`**; Verification >1M chars, **pathological**; 300-item claim cap | Unchanged AI cost for the same schemas; expansion linear and deterministic; dossier bounded |
| Many requirements | Each costs probe verdicts | Triage is deterministic |
| Many ambiguities | Per row/wording | Per slot or anomaly signature |

**Where pathology remains in the target:**
- prose-dominated documents, where cost falls back to today's extraction minus dismissals;
- many *distinct* table schemas (S grows);
- ESC `requirements_of` is O(rules × assertions) of deterministic CPU, which is later work.

---

## 8. Risks and containment

| Risk | Containment |
|---|---|
| A Reading silently over-generalises | Conformance checks and anomalies (§3.5); samples plus every anomaly in the dossier; a single Reading objection supersedes all its instances |
| I2 becomes vacuous | Expanded claims are `structural`, with mandatory, complete `basis_refs`; tests in Phase 2 |
| The DEM drifts into semantics | Import boundary, field allow-list and catalogue-independence tests (Phase 1) |
| Bad table recovery (scans, odd layouts) | Two fallbacks: (1) uncertain structure already degrades to text blocks (today's path); (2) a Reading may set the Reading-level status `not_a_table` for a recovered region, which then owns nothing and returns its segments to prose extraction |
| Segment ids drift, breaking `EvidenceReference.locator` | The Phase 0 id-stability test; cell ids are suffixes only |
| Replay fixtures are invalidated | Legacy fixtures keep running in claims mode until Phase 6; new captures via the Phase 0 command |
| Dual-mode maintenance | A time-boxed flag; Phase 6 is part of the plan and is gated on evidence |
| Negative states collapse again | A derived `Requirement.state`, asserted in Phase 4 tests and the regression matrix |
| The oracle shows the ontology itself blocks reasonable results | Reported as a model-design finding, not coded around |

**Backward compatibility**
- **Canonical models, Proposals, ProposalChanges and ChangeSet v3:** untouched.
- **EvidenceReference:** same fields.
- **Assisted interfaces:** `run_ai_operation`, `OperationResult` and the outcome policies are unchanged. New stage names show up in `stage_summary` and `AIExecutionStep.stage`.
- **Traces:** the format is unchanged, plus the DEM digest and Readings in the snapshot.
- **Not part of this plan:** there is still no path for a human to answer open decisions. The small number of Reading slots and `undecidable` questions makes a later reviewer-answer UI realistic.

---

## 9. Recommendation

**A substantial architectural refactoring. Not a modest refactor, and not a rewrite.**

**Why not a modest refactor.** The responsibility boundaries change:
- structure becomes a first-class deterministic layer;
- the AI's semantic unit moves from per-instance claims to schema-level Readings;
- coverage, probing and verification move from "argue with per-row output" to "triage from structure, and review causes".

**Why not a rewrite.** The governance core survives, roughly two-thirds of the code, and it is the hardest part to get right:
- the EvidenceGraph, ingress and provenance;
- identity and ESC;
- observations and conflicts;
- the compiler, TracePolicy, resolution, staging and commit;
- the engine, Adjudication, tracing and replay.

The change is concentrated in the AI-facing front end and in Verification's input. Every phase ships behind the mode flag with the existing suite green.

**First step.** Phase 0's governance contract, which separates governance defects from interpretation defects before anything is refactored.

## Verification of this plan (once implemented)
- `python manage.py test ai` stays green in both modes after every phase. `npm test` is unaffected.
- Phase 0: `python manage.py test ai.tests.test_governance_contract`.
- Live comparison per phase: `ONYXJAR_LIVE_AI_TESTS=1 python manage.py test ai.tests.test_evidence_lifecycle.LiveInternationalFlyerTests ai.tests.test_reconcile_workflow.LiveRugbyTests`. Run once with `AI_RECONCILE_EVIDENCE_MODE=claims` and once with `readings`, with `AI_TRACE_DIR` set. Compare the outcome, the blocked causes and their negative states against §0, then calls and payload chars against §7.

---

## Architectural invariants

1. **The DEM is structural, never semantic.** It holds no ontology types, relationships or options. This is enforced by import-boundary, field allow-list and catalogue-independence tests.
2. **Reading is the semantic interpretation of document structure.** It is made once per table or section schema, in bounded batches whose AI cost scales with the number of schemas, never rows. It chooses from OnyxJar-offered options plus `none` / `undecidable`, with a verbatim basis. Its ownership of DEM elements is explicit and element-level; descendant prose it does not interpret stays with prose extraction.
3. **Deterministic expansion never invents ontology meaning independently of a Reading.** `expand(dem, [])` is empty.
4. **Every derived structural claim is causally attributable to its Reading and its exact DEM evidence.** It carries `origin = reading` and `basis_refs` listing every contributing `reading_id@revision` (no dependency is dropped in favour of a primary one); it is ledgered `structural` over all contributing `read:` claims and DEM cells; a change to any contributing Reading invalidates it; and the chain change → claim → Reading → DEM is traversable.
5. **Nonconforming rows do not silently inherit a Reading.** A row is expanded only if it passes both `structurally_conforms` (DEM) and `reading_conforms` (Reading). Otherwise it becomes an anomaly, handled deterministically or by grouped AI decisions.
6. **`undecidable`, `insufficient_evidence` and `not_stated` stay distinct, and a Reading `none` is none of them.** `none` is a semantic decision about a structural element, can be challenged by later structural evidence, and never directly produces `not_stated`. `not_stated` is never recorded while a structural lead sits in an unread, undecided or unreconsidered `none` element.
7. **Deterministic governance stays authoritative** for requirements, cardinality, closure, compilation and commit.
8. **Legacy claims mode stays available** (including the completed `not_stated` contest safeguard) until readings mode is proven at the Phase 5 gate. It is retired only in Phase 6.
9. **Semantic correction targets the highest-leverage decision.** A Reading slot is corrected once and re-expanded. No per-row semantic correction exists for rows that conform to a Reading.
10. **Semantic ownership is explicit, element-level and non-overlapping.** Each interpretation scope has at most one active owner; a Section Reading never owns table cells. One deterministic projection, `owned_source_segments`, sets the prose-extraction boundary, and containment alone never excludes a segment. A `not_a_table` Reading owns nothing.
11. **Unresolved anomalies block terminal negatives.** A relevant unresolved anomaly routes through the grouped `row_exception` / Reading decision path before any `not_stated` or `insufficient_evidence` is recorded. If the budget prevents resolution, the state is `unadjudicated`, never a false negative.
12. **No structured shortcut around Reading.** Once the DEM recognises content as structured, it reaches semantic claims only through a Reading. Prose eligibility is decided by DEM classification (`prose_eligible`). Only `not_a_table`, or a DEM classification as prose, makes structured content prose-eligible. A pending, rejected or superseded Reading never does.
13. **Every decided Reading slot has a sufficient structural basis.** Normally that is header or section context plus representative row cells. With no data rows, the header or section context alone may be sufficient. Sample evidence is never fabricated.
14. **Candidate recall.** Deterministic candidate generation may rank, prioritise and slice, but never makes an ontology-compatible interpretation unreachable because of lexical mismatch. Reading responses carry catalogue references as opaque strings, never shortlist enums, and an outside-slice key is validated against the full catalogue.
15. **Reading-derived claims are already mapped.** A selected ontology option in a Reading slot is the mapping decision. Reading-derived claims bypass lexical predicate mapping, relationship inference and AI mapping, and keep only the deterministic legality checks. `mapping.py` serves Reading candidate generation, never a second interpretation after expansion.
16. **`not_a_table` is constrained.** It is valid only for structure unsuitable for table interpretation (layout grid, form, decorative alignment, unusable recovery), with a structural basis. It is never a substitute for `none` / `undecidable` in a valid table, and it is always reviewable.
17. **Semantic row exceptions come from the Reading.** `reading_conforms` combines only DEM structural facts with Reading-declared exceptions. It validates the consequences of the Reading's decisions and never interprets raw strings; surface-text overlap alone is never an anomaly.
18. **Ids are deterministic.** The same segmented source always gives the same segment, column, cell, Reading, slot and expanded-claim ids. That keeps ProposalChange → claim → Reading → cell → segment reproducible.
