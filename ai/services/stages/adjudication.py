"""
Reconcile stage -- Adjudication: OnyxJar's typed questions -> chosen option
ids, each a claim with the verbatim text it rests on.

Every open question of the current analysis is asked in one call (questions
about the same wording between the same kinds are already one pattern
question). The payload is local evidence, as everywhere else: the segments
the questions' own claims cite, plus the headings/tables they sit under,
each citable by id.

OnyxJar generated every option, so an answer is valid only if it names one of
its question's options and (unless "undecidable") rests on verbatim text:
`citations` quote segments (one citation per segment -- a table's header row
and a data row are two citations), or `excerpt` quotes the intent. A valid
answer is pinned and honoured by every later recomputation. An invalid one is
re-asked alone, once, in a correction call (its own budget,
`adjudication_correction`: a correction never consumes a round); a second
failure records `rejected_answer` -- not a claim, never re-asked, never a
basis for anything (ambiguity preserved, nothing forced).

The workflow re-enters this stage whenever a later analysis has new open
questions (a probe's or a reviewer's claims raise them) and a round is left.
"""

from __future__ import annotations

from django.conf import settings

from ai.services.evidence_bundle import excerpt_occurs
from ai.services.feedback import issue
from ai.services.provenance import excerpt_in_any_source
from ai.services.reconcile import questions as q
from ai.services.reconcile.responses import AdjudicationResult
from ai.services.sources import with_ancestors
from ai.services.stages import prompts
from ai.services.workflow.engine import Correct, Goto, Stage


def evidence_payload(bundle) -> list[dict]:
    budget, sources = settings.AI_VERIFY_EVIDENCE_MAX_CHARS, []
    for source in bundle.sources:
        text = source.text[: max(budget, 0)]
        budget -= len(text)
        sources.append({"source_id": source.source_id, "name": source.name, "text": text, "truncated": len(text) < len(source.text)})
    return sources


def question_segments(question, analysis) -> list[str]:
    """The segments the question's own claims cite (entities, assertions,
    facts, or a cluster's mentions)."""

    graph, found = analysis.graph, []
    for subject in question.subject_ids:
        item = graph.entity(subject) or graph.assertion(subject) or graph.fact(subject)
        if item is not None:
            provenance = item.provenance
        elif subject in analysis.clusters.clusters:
            provenance = analysis.clusters.clusters[subject].provenance
        else:
            provenance = []
        found += [p.segment_id for p in provenance if p.segment_id and p.segment_id not in found]
    return found


def answer_issue(question_id, option_id, options, *, citations=(), excerpt="", bundle, intent_text, exempt=(q.UNDECIDABLE,)):
    """-> an AIIssue when an answer is not acceptable as a claim, else None.
    The same check applies to Adjudication answers and to a reviewer's
    answer to a decision (Verification)."""

    if option_id not in options:
        return issue("invalid_option", f"'{option_id}' is not an option of this question; choose one of {', '.join(sorted(options))}.",
                     item_id=question_id)
    if option_id in exempt:
        return None
    for citation in citations:
        segment = bundle.segment(citation.segment_id)
        if segment is None:
            return issue("unknown_segment", f"Your choice may stand, but it cites segment '{citation.segment_id}', which does not exist; "
                         "cite the segments shown, by segment_id.", item_id=question_id)
        if not excerpt_occurs(citation.excerpt, segment.text):
            return issue(
                "excerpt_not_found",
                f"Keep your choice if it is right, but fix the citation: \"{(citation.excerpt or '')[:120]}\" does not occur in segment "
                f"'{citation.segment_id}'. Quote that segment's own text; cite each segment (e.g. a table's header row and a data row) "
                "separately.", item_id=question_id,
            )
    if citations:
        return None
    if excerpt_in_any_source(excerpt, bundle=bundle, intent_text=intent_text):
        return None
    return issue("excerpt_not_found", "Keep your choice if it is right, but cite the segment(s) it rests on (segment_id + verbatim "
                 "excerpt of that segment), or quote the intent verbatim in `excerpt`.", item_id=question_id)


class AdjudicationStage(Stage):
    stage_id = "adjudication"
    response_schema = AdjudicationResult

    def system_prompt(self, run) -> str:
        return prompts.preamble(run.operation) + prompts.ADJUDICATION

    def questions(self, run) -> list:
        rs = run.state.reconcile
        return rs.reask_questions or list(rs.analysis.questions)

    def build_input(self, run) -> dict:
        state = run.state
        rs = state.reconcile
        questions = self.questions(run)
        rs.reask_questions = questions
        per_question = {question.question_id: question_segments(question, rs.analysis) for question in questions}
        budget, shown = settings.AI_VERIFY_EVIDENCE_MAX_CHARS, []
        for segment in with_ancestors(run.bundle, [sid for ids in per_question.values() for sid in ids]):
            if len(segment.text) <= budget:
                shown.append(segment)
                budget -= len(segment.text)
        shown_ids = {segment.segment_id for segment in shown}
        payload = {
            "stage": self.stage_id,
            "intent": run.intent.text,
            "model": run.model_context(),
            "segments": [segment.context() for segment in shown],
            "questions": [
                {**question.model_dump(mode="json"), "segment_ids": [s for s in per_question[question.question_id] if s in shown_ids]}
                for question in questions
            ],
            "feedback": [item.model_dump(mode="json", exclude_none=True) for item in state.feedback.get(self.stage_id, [])],
        }
        if not shown:
            # Nothing cites a segment (e.g. a question about the request
            # itself): the bounded source text instead.
            payload["evidence"] = evidence_payload(run.bundle)
        return payload

    def evaluate(self, run, output: AdjudicationResult):
        rs = run.state.reconcile
        questions = {question.question_id: question for question in rs.reask_questions}
        answered, issues = set(), []
        for answer in output.answers:
            question = questions.get(answer.question_id)
            if question is None or answer.question_id in answered:
                continue
            found = answer_issue(question.question_id, answer.option_id, question.option_ids(), citations=answer.citations,
                                 excerpt=answer.excerpt, bundle=run.bundle, intent_text=run.intent.text)
            if found is not None:
                issues.append(found)
                continue
            quoted = " ... ".join(c.excerpt for c in answer.citations) or answer.excerpt
            rs.pins[question.question_id] = q.Pin(option_id=answer.option_id, basis="adjudicated", excerpt=quoted, note=answer.note)
            answered.add(question.question_id)
        for question_id in questions.keys() - answered:
            if not any(i.item_id == question_id for i in issues):
                issues.append(issue("unanswered", "This question needs an answer (use 'undecidable' if the evidence cannot decide it).", item_id=question_id))

        rs.asked |= set(questions)
        retry = []
        for found in issues:
            if found.item_id in rs.question_failures:
                rs.pins.setdefault(found.item_id, q.Pin(option_id=q.UNDECIDABLE, basis="rejected_answer", reason=found.message))
            else:
                rs.question_failures.add(found.item_id)
                retry.append(found)
        if retry and run.allows(self.stage_id, correction=True):
            rs.reask_questions = [questions[i.item_id] for i in retry if i.item_id in questions]
            return Correct(retry)
        for found in retry:
            rs.pins.setdefault(found.item_id, q.Pin(option_id=q.UNDECIDABLE, basis="rejected_answer", reason=found.message))
        rs.reask_questions = []
        return Goto("analysis")
