"""
Reconcile stage -- Verification: an independent, success-biased reviewer.

Input (the smallest contract that still lets it catch upstream errors):
the raw intent and the IntentFrame; the source text (all of it within
AI_VERIFY_EVIDENCE_MAX_CHARS, otherwise the sources that mention in-scope
entities first, with the rest declared as not shown); the Decision Ledger
(claims and structural decisions, each with its options); the projected
changes joined to the evidence and decisions each rests on (ChangeTrace +
ProjectedDelta); and the blocked targets. Never the raw ChangeSet, the full
catalogue or the canonical model.

Output: typed objections. A material objection is routed by the step that
produced the decision it targets -- never by its advisory `kind` -- back to
the earliest point that can correct it, as a claim (basis "verifier"):

    evidence item      -> retracted (the source doesn't say that)
    mapping/identity/  -> the decision's question is pinned to the reviewer's
    normalise/target      option (validated against that decision's options)
    adjudication answer-> re-pinned
    merge              -> its mentions pinned distinct
    scope selection    -> the item excluded
    source segment     -> the missed evidence appended (validated)
    action             -> its subject excluded (unsupported change)
    intent             -> frame amendment (quoting the intent), or, with >=2
                          readings that change the result, clarification

and the deterministic pipeline re-runs -- any decision or evidence gap the
new claim creates re-enters Adjudication / Gap Probe under their own budgets
(ai.services.stages.reconcile_steps). A reviewer's answer to a decision is a
claim like an Adjudication answer and is validated the same way (one of the
decision's options; verbatim text, except for the withdrawing 'none' /
'undecidable'). An unroutable objection is re-asked once (its own budget,
`verification_correction`); a repeated or still-unroutable material
objection is never re-routed: it ends the run UNRESOLVED with findings.
"""

from __future__ import annotations

from django.conf import settings

from ai.services.artifacts import Finding
from ai.services.evidence_graph import item_id, validate_evidence_graph
from ai.services.reconcile.ingress import ingest, log
from ai.services.grounding import grounding_issues
from ai.services.reconcile.coverage import DISMISSED, UNCOVERED
from ai.services.sources import mentions, with_ancestors
from ai.services.feedback import AIIssue, issue
from ai.services.intent_frame import amend, repair_elisions, validate_intent_frame
from ai.services.reconcile import questions as q
from ai.services.reconcile.ledger import ADJUDICATION, EXTRACTION, IDENTITY, MAPPING, NORMALISE, SCOPE
from ai.services.reconcile.responses import VerificationResult
from ai.services.result_schema import OperationOutcome
from ai.services.stages import prompts
from ai.services.stages.adjudication import answer_issue
from ai.services.stages.commit import commit, commit_decision
from ai.services.workflow.engine import Correct, Finish, Goto, Stage

_EXTRA_OPTIONS = {
    q.NONE, q.UNDECIDABLE, q.NEW, "refers_to_intermediate", "direct_statement", "same", "distinct", "contradictory",
    "update", "keep", "confirm", "reject",
}


def _latest_ingress(rs) -> list[dict]:
    latest = {}
    for entry in rs.ingress_log:
        latest[entry["id"]] = entry
    return list(latest.values())


def select_segments(bundle, names, priority_ids) -> tuple[list[dict], int]:
    """Local, bounded evidence for the reviewer: everything when it fits;
    otherwise the dismissed/uncovered segments first, then segments
    mentioning in-scope names, then the rest, in document order. Returns the
    segment contexts shown and how many were left out."""

    segments = list(bundle.segments())
    budget = settings.AI_VERIFY_EVIDENCE_MAX_CHARS
    if sum(len(s.text) for s in segments) <= budget:
        return [s.context() for s in segments], 0
    ranked = sorted(
        segments,
        key=lambda s: (s.segment_id not in priority_ids, not mentions(s.text, names), s.source_id, s.position),
    )
    chosen = set()
    for segment in ranked:
        if len(segment.text) <= budget:
            chosen.add(segment.segment_id)
            budget -= len(segment.text)
    shown = [s.context() for s in with_ancestors(bundle, [s.segment_id for s in segments if s.segment_id in chosen])]
    return shown, len(segments) - len(shown)


class VerificationStage(Stage):
    stage_id = "verification"
    response_schema = VerificationResult

    def system_prompt(self, run) -> str:
        return prompts.preamble(run.operation) + prompts.VERIFICATION

    def build_input(self, run) -> dict:
        state = run.state
        rs = state.reconcile
        analysis = rs.analysis
        change_set, trace = rs.compiled if rs.compiled else (state.change_set, None)
        names = [analysis.cluster_name(c) for c in analysis.scope.tentative | analysis.scope.anchor_clusters]
        dismissed = [c for c in analysis.coverage.values() if c.status == DISMISSED]
        uncovered = [c for c in analysis.coverage.values() if c.status == UNCOVERED]
        segments, omitted = select_segments(run.bundle, names, {c.segment_id for c in (*dismissed, *uncovered)})
        changes = []
        for action in (change_set.actions if change_set else []):
            entry = trace.entries.get(action.action_id) if trace else None
            changes.append({
                "action_id": action.action_id,
                "kind": action.kind,
                "rationale": action.rationale,
                "evidence": [p.model_dump(mode="json", exclude_none=True) for p in action.provenance],
                "decision_ids": entry.decision_ids if entry else [],
            })
        feedback = state.feedback.get(self.stage_id, [])
        previous = state.previous_output.get(self.stage_id) if feedback else None
        return {
            "stage": self.stage_id,
            "intent": run.intent.text,
            "model": run.model_context(),
            "intent_frame": rs.frame.model_dump(mode="json"),
            "evidence_segments": segments,
            "segments_not_shown": omitted,
            "dismissed_segments": [
                {"segment_id": c.segment_id, "reason": c.reason, "mentions": c.named, "flagged": c.flagged,
                 "text": run.bundle.segment(c.segment_id).text}
                for c in sorted(dismissed, key=lambda c: not c.flagged)
            ],
            "uncovered_segments": [
                {"segment_id": c.segment_id, "mentions": c.named, "text": run.bundle.segment(c.segment_id).text} for c in uncovered
            ],
            "decision_ledger": analysis.ledger.payload(),
            "changes": changes,
            "projected_delta": state.delta.model_dump(mode="json") if state.delta is not None else None,
            # Each with what the evidence states vs what can be added, and the
            # cascade down to its root cause -- object to the root, not the symptom.
            "blocked_targets": state.blocked_targets,
            # Every explicit intent target and what became of it: requested
            # work that is unframed / unmapped / undecided / not_evidenced was
            # NOT done (never a no-op).
            "intent_targets": analysis.target_status,
            # Decisions left unadjudicated because the budget was spent (not
            # because the evidence is silent), with the claims they hold back.
            "open_decisions": [
                {"question_id": question.question_id, "kind": question.kind, "prompt": question.prompt,
                 "options": [o.option_id for o in question.options], "subject_ids": question.subject_ids,
                 "decision_ids": sorted(d.decision_id for d in analysis.ledger.decisions.values() if d.question_key == question.question_id
                                        or (d.decision_id.startswith("map:") and d.decision_id[4:] in question.subject_ids))}
                for question in analysis.questions
            ],
            # Claims that never entered the graph, and why.
            "rejected_claims": [e for e in _latest_ingress(rs) if e["outcome"] in ("rejected", "dropped", "dropped_dependant", "invalid")],
            "notes": [f.model_dump(mode="json") for f in state.plan_findings],
            "feedback": [item.model_dump(mode="json", exclude_none=True) for item in feedback],
            "previous_output": previous.model_dump(mode="json") if previous is not None else None,
        }

    def evaluate(self, run, output: VerificationResult):
        state = run.state
        rs = state.reconcile
        material = [o for o in output.objections if o.severity == "material"]
        notes = [Finding(severity="minor" if o.severity == "minor" else "info", message=o.message) for o in output.objections if o.severity != "material"]

        if not material:
            state.review_notes = notes
            state.unresolved_findings = [f for f in state.unresolved_findings if f.severity == "material"]  # blocked targets stay reported
            completeness = "partial" if state.blocked_targets else "complete"
            if not state.change_set or not state.change_set.actions:
                if state.blocked_targets:
                    return Finish(OperationOutcome.UNRESOLVED, explanation="None of the requested items could be reconciled from the evidence.",
                                  blocked_targets=state.blocked_targets)
                return Finish(OperationOutcome.NO_CHANGE_REQUIRED, explanation=output.summary or state.interpretation or "No changes were needed.")

            def retry_after_commit_failure(issues):
                state.last_issues = list(issues)
                if rs.compile_retries < 1:
                    rs.compile_retries += 1
                    return Goto("analysis", correction=True)
                return Finish(OperationOutcome.UNRESOLVED, explanation="The changes could not be committed against the current model.",
                              unresolved_issues=list(issues), blocked_targets=state.blocked_targets)

            decision = commit_decision(run, commit(run), on_issues=retry_after_commit_failure)
            if isinstance(decision, Finish) and decision.proposal is not None:
                decision.completeness = completeness
                decision.blocked_targets = state.blocked_targets
            return decision

        routed, invalid, clarification, leftover = 0, [], None, []
        for objection in material:
            fingerprint = (objection.kind, objection.target_kind, objection.target_id, objection.option_id)
            if fingerprint in rs.objections_seen:
                leftover.append(objection)
                continue
            outcome = self.route(run, objection)
            if isinstance(outcome, AIIssue):
                invalid.append(outcome)
                leftover.append(objection)
            elif isinstance(outcome, str):
                clarification = outcome
            else:
                rs.objections_seen.add(fingerprint)
                routed += 1

        state.review_notes = notes
        if clarification:
            return Finish(OperationOutcome.NEEDS_USER_CLARIFICATION, explanation=clarification)
        if invalid and not routed and run.allows(self.stage_id, correction=True):
            return Correct(invalid)
        if routed:
            state.last_issues = [AIIssue(code=f"review_{o.kind}", message=o.message) for o in material]
            return Goto("analysis", correction=True)
        state.unresolved_findings = [*state.unresolved_findings, *(Finding(severity="material", message=o.message) for o in leftover)]
        state.last_issues = [AIIssue(code=f"review_{o.kind}", message=o.message) for o in leftover]
        return Finish(OperationOutcome.UNRESOLVED, explanation=run.explain(state.last_issues), unresolved_issues=state.last_issues,
                      blocked_targets=state.blocked_targets)

    # -- routing ---------------------------------------------------------------------

    def route(self, run, objection):
        """-> None (routed) | AIIssue (not actionable as given) | str (clarification question)."""

        rs = run.state.reconcile
        analysis = rs.analysis
        target = objection.target_id

        if objection.target_kind == "segment":
            if objection.evidence.is_empty():
                return issue("unroutable_objection", "missed_evidence must give the missed claims in `evidence`.", item_id=objection.objection_id)
            keyed, _, found = ingest(objection.evidence.with_origin("verifier"), rs=rs, bundle=run.bundle, origin="verifier")
            found += validate_evidence_graph(keyed, bundle=run.bundle, intent_text=run.intent.text, known_ids=frozenset(rs.graph.ids()))
            found += grounding_issues(keyed, bundle=run.bundle, known=rs.graph)
            if found:
                for item in keyed.items():
                    log(rs, item_id(item), origin="verifier", outcome="invalid", reason=found[0].message)
                return issue("unroutable_objection", "; ".join(f.message for f in found[:5]), item_id=objection.objection_id)
            rs.graph = rs.graph.appended(keyed)
            for item in keyed.items():
                log(rs, item_id(item), origin="verifier", outcome="accepted")
            return None

        if objection.target_kind == "intent":
            if objection.kind == "intent_ambiguous":
                if len(objection.readings) < 2:
                    return issue("unroutable_objection", "intent_ambiguous needs at least two readings.", item_id=objection.objection_id)
                return "The request could mean: " + " / ".join(objection.readings) + ". Which is intended?"
            if objection.frame_amendment is None:
                return issue("unroutable_objection", "frame_error needs a frame_amendment.", item_id=objection.objection_id)
            amended, repaired = repair_elisions(amend(rs.frame, objection.frame_amendment), run.intent.text)
            found = validate_intent_frame(amended, run.intent.text)
            if found:
                return issue("unroutable_objection", "; ".join(f.message for f in found[:5]), item_id=objection.objection_id)
            rs.frame = amended
            rs.frame_repairs.update(repaired)
            # A restored (or explicitly withdrawn) unframed element is settled.
            amendment = objection.frame_amendment
            for identifier in [*(t.target_id for t in amendment.add_targets), *(a.anchor_id for a in amendment.add_anchors),
                               *amendment.remove_target_ids]:
                rs.unframed.pop(identifier, None)
            if amendment.include_related is not None:
                rs.unframed.pop("include_related", None)
            return None

        if objection.target_kind == "action":
            _, trace = rs.compiled if rs.compiled else (None, None)
            entry = trace.entries.get(target) if trace else None
            if entry is None:
                return issue("unroutable_objection", f"'{target}' is not an action id.", item_id=objection.objection_id)
            rs.excluded.add(entry.subject)
            return None

        decision = analysis.ledger.get(target)
        if decision is None:
            return issue("unroutable_objection", f"'{target}' is not a decision id in the ledger.", item_id=objection.objection_id)
        if decision.kind == "claim" and decision.step == EXTRACTION:
            rs.retracted.add(target)
            return None
        if decision.step == ADJUDICATION and target.startswith("adj:"):
            key = target[4:]
            found = self._answer_issue(run, objection, self._options_for(analysis, key))
            if found is not None:
                return found
            rs.pins[key] = q.Pin(option_id=objection.option_id, basis="verifier", excerpt=objection.excerpt or "", note=objection.message)
            return None
        if target.startswith("cluster:") and decision.step == NORMALISE:
            members = list(decision.subject_ids)
            for position, a in enumerate(members):
                for b in members[position + 1:]:
                    rs.pins[q.key("coreference", a, b)] = q.Pin(option_id="distinct", basis="verifier", excerpt=objection.excerpt or "", note=objection.message)
            return None
        if decision.step in (MAPPING, IDENTITY, NORMALISE, SCOPE) and decision.question_key and not target.startswith("esc:"):
            found = self._answer_issue(run, objection, {o["option_id"] for o in decision.options} | _EXTRA_OPTIONS)
            if found is not None:
                return found
            rs.pins[decision.question_key] = q.Pin(option_id=objection.option_id, basis="verifier", excerpt=objection.excerpt or "", note=objection.message)
            return None
        if target.startswith("esc:"):
            rs.excluded.add(target[4:])
            return None
        return issue("unroutable_objection", "Target the decision where the problem originates (see its step).", item_id=objection.objection_id)

    @staticmethod
    def _answer_issue(run, objection, options):
        """A reviewer's answer to a decision is a claim: validated exactly as
        an Adjudication answer ('none'/'undecidable' only withdraw support,
        so they need no quote)."""

        found = answer_issue(objection.objection_id, objection.option_id, options, excerpt=objection.excerpt or "",
                             bundle=run.bundle, intent_text=run.intent.text, exempt=(q.NONE, q.UNDECIDABLE))
        if found is None:
            return None
        if found.code == "invalid_option":
            return issue("unroutable_objection", f"Give option_id: one of {', '.join(sorted(options))}.", item_id=objection.objection_id)
        return issue("unroutable_objection", "Quote, verbatim in `excerpt`, the source or intent text this answer rests on.",
                     item_id=objection.objection_id)

    @staticmethod
    def _options_for(analysis, key) -> set:
        for decision in analysis.ledger.decisions.values():
            if decision.question_key == key:
                return {o["option_id"] for o in decision.options} | _EXTRA_OPTIONS
        return set(_EXTRA_OPTIONS)
