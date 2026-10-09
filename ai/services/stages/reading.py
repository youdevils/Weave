"""
Reconcile stage -- Reading (readings mode only): the AI's schema-level
interpretation of the evidence's tables and the headings above them
(ai.services.reconcile.readings).

OnyxJar lays out every element's slots from the DEM, packs elements into
bounded batches (AI_READING_BATCH_MAX_CHARS -- AI cost scales with the
number of schemas, never rows), and validates each answer locally: slot ids,
options against the FULL catalogue, relationship legality between the types
chosen, and the structural basis each decided slot cites. An element whose
answer breaks that contract is re-asked once in the batch's correction (its
own scoped budget); after that its invalid slots settle as rejected and
nothing is expanded from them. Then Extraction reads the prose -- and only
the prose (`readings.prose_eligible`).
"""

from __future__ import annotations

from django.conf import settings

from ai.services.reconcile import readings as rd
from ai.services.reconcile.responses import ReadingResult
from ai.services.reconcile.state import ReconcileState
from ai.services.semantic.catalogue import build_catalogue
from ai.services.semantic.index import SemanticModelIndex
from ai.services.stages import prompts
from ai.services.workflow.engine import Correct, DeterministicStage, Goto, Stage


def _settle(run) -> None:
    """After the last batch: what prose extraction may see, and what no AI
    claim may cite."""

    rs = run.state.reconcile
    document = run.bundle.document()
    rs.prose_scope = rd.prose_eligible(document, rs.readings)
    rs.locked_segments = rd.locked_segments(document, rs.readings)


class ReadingPlanStage(DeterministicStage):
    """Lays out every structured element's slots from the DEM and packs them
    into batches; with nothing structured to read, goes straight to the
    prose (no provider call)."""

    stage_id = "reading_plan"

    def run(self, run):
        state = run.state
        if state.reconcile is None:
            state.reconcile = ReconcileState(evidence_mode="readings")
        rs = state.reconcile
        state.index = SemanticModelIndex.load(run.model)
        state.catalogue = build_catalogue(state.index)
        document = run.bundle.document()
        rs.reading_elements = {e.element_id: e for e in rd.skeleton(document, run.bundle, state.index)}
        rs.reading_batches = rd.plan_reading_batches(list(rs.reading_elements.values()), settings.AI_READING_BATCH_MAX_CHARS)
        rs.reading_batch_index = 0
        if not rs.reading_batches:
            _settle(run)
            return Goto("extraction")
        return Goto("reading")


class ReadingStage(Stage):
    stage_id = "reading"
    response_schema = ReadingResult

    def system_prompt(self, run) -> str:
        return prompts.preamble(run.operation) + prompts.READING

    def _elements(self, run) -> dict:
        return run.state.reconcile.reading_elements

    def build_input(self, run) -> dict:
        state = run.state
        rs = state.reconcile
        elements = self._elements(run)
        batch = rs.reading_batches[rs.reading_batch_index]
        feedback = state.feedback.get(self.stage_id, [])
        if feedback:
            # The correction re-asks only the elements whose reading broke the contract.
            batch = [i.item_id for i in feedback if i.item_id in elements]
        payload = {
            "stage": self.stage_id,
            "intent": run.intent.text,
            "model": run.model_context(),
            "catalogue": state.catalogue.model_dump(mode="json"),
            "catalogue_note": "Slot options are a ranked shortlist; any key of this catalogue may be chosen.",
            "batch": {"number": rs.reading_batch_index + 1, "of": len(rs.reading_batches)},
            "elements": [elements[element_id].payload for element_id in batch],
        }
        if feedback:
            payload["feedback"] = [i.model_dump(mode="json", exclude_none=True) for i in feedback]
            previous = state.previous_output.get(self.stage_id)
            if previous is not None:
                payload["previous_output"] = previous.model_dump(mode="json")
        return payload

    def evaluate(self, run, output: ReadingResult):
        state = run.state
        rs = state.reconcile
        elements = self._elements(run)
        correcting = bool(state.feedback.get(self.stage_id))
        asked = [i.item_id for i in state.feedback[self.stage_id]] if correcting else rs.reading_batches[rs.reading_batch_index]
        final = correcting or not run.allows(self.stage_id, correction=True)
        answered = rd.apply_result(output, {e: elements[e] for e in asked if e in elements}, run.bundle.document(), run.bundle,
                                   state.index, final=final)
        rs.readings = [r for r in rs.readings if r.element_id not in {n.element_id for n in answered.readings}] + answered.readings
        if answered.issues and not final:
            return Correct(answered.issues)

        rs.reading_batch_index += 1
        if rs.reading_batch_index < len(rs.reading_batches) and run.allows(self.stage_id):
            run.open_scope("reading_correction")
            return Goto(self.stage_id)
        for batch in rs.reading_batches[rs.reading_batch_index:]:
            # Batches the budget never reached: unread structure, never prose.
            rs.readings += [rd._unanswered(elements[e], run.bundle.document()) for e in batch if e in elements]
        _settle(run)
        return Goto("extraction")
