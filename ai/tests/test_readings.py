"""
Readings -- Phase 2 of .Documentation/reconcile-architecture-plan.md:
schema-level interpretation of document structure (ai.services.reconcile.
readings, ai.services.stages.reading) and its deterministic expansion into
the unchanged governance core.

The flyer's ideal Reading is scripted (a Responders provider answers each
stage from what it was sent); everything after it is OnyxJar.
"""

from django.test import override_settings

from ai.services.evidence_bundle import EvidenceBundle
from ai.services.evidence_graph import EvidenceGraph
from ai.services.orchestrator import run_ai_operation
from ai.services.reconcile import questions as q
from ai.services.reconcile import readings as rd
from ai.services.reconcile.analysis import run_analysis
from ai.services.reconcile.compiler import compile_change_set
from ai.services.reconcile.ingress import ingest
from ai.services.reconcile.responses import (
    DemCitation,
    ElementReading,
    ExtractionResult,
    ProbeResult,
    ReadingException,
    ReadingResult,
    ReadingSectionRelation,
    ReadingSlotAnswer,
)
from ai.services.reconcile.state import ReconcileState
from ai.services.reconcile.trace_policy import check_trace
from ai.services.result_schema import OperationOutcome
from ai.services.semantic.index import SemanticModelIndex
from ai.tests.reference import assert_reference, evaluate, load_spec, norm, outcome_from_proposal
from ai.tests.support import approve, nothing_stated
from ai.tests.test_governance_contract import INTENT, TITLE, GovernanceContractTestCase, cite, ent, rel
from ai.tests.test_reconcile_resilience import Responders

TEAM_COLUMNS = ("S1#t1.c2", "S1#t1.c3", "S1#t1.c4", "S1#t1.c5")


class ReadingFixture(GovernanceContractTestCase):
    """The live flyer model and PDF; readings built from a declarative plan."""

    def setUp(self):
        super().setUp()
        self.bundle_ = EvidenceBundle.from_assets(self.assets)
        self.document = self.bundle_.document()
        self.index = SemanticModelIndex.load(self.model)

    # -- building ideal Reading answers ---------------------------------------------

    def basis(self, *dem_ids):
        return [DemCitation(dem_id=d, excerpt=rd.dem_text(d, self.document, self.bundle_)) for d in dem_ids]

    def table_plan(self, *, t3_relation="played_at:as_stated", t4_exception=True, t4_exception_decided=True):
        """element id -> (slots {short slot: (choice, basis ids, extra)}, section relations, exceptions)."""

        def fixture_table(t, exception, relation="played_at:as_stated"):
            row = f"{t}.r1"
            plan = {
                "role/c1": ("stage", [f"{t}.c1", f"{row}.c1"], {}),
                "role/c2": ("match", [f"{t}.c2", f"{row}.c2"], {}),
                "split/c2": ("team", [f"{t}.c2", f"{row}.c2"], {"part_relation": "has_team:as_stated"}),
                "role/c3": ("venue", [f"{t}.c3", f"{row}.c3"], {}),
                "relation/c1>c2": ("has_match:as_stated", [f"{t}.c1", f"{t}.c2", f"{row}.c1"], {}),
                "relation/c1>c3": ("none", [f"{t}.c1", f"{t}.c3", f"{row}.c1"], {}),
                "relation/c2>c3": (relation, [f"{t}.c2", f"{t}.c3", f"{row}.c2"], {}),
            }
            exceptions = [ReadingException(row_ids=[f"{t}.r1", f"{t}.r2"], slot_id=f"rd/{t}/split/c2", kind="placeholder",
                                           decided=t4_exception_decided, reason="The parts are pool positions, not named teams.")] if exception else []
            return plan, [], exceptions

        teams = {f"role/c{k}": ("team", ["S1#5", f"S1#t1.r1.c{k}"], {}) for k in range(2, 6)}
        teams["role/c1"] = ("stage", ["S1#5", "S1#t1.r1.c1"], {})
        teams.update({slot.slot_id.split("/", 2)[-1]: ("none", ["S1#5", "S1#t1.r1.c1"], {})
                      for slot in self.element("S1#t1").slots if slot.kind == "relation"})
        venues = {
            "role/c1": ("venue", ["S1#t2.c1", "S1#t2.r1.c1"], {}), "role/c2": ("value", ["S1#t2.c2", "S1#t2.r1.c2"], {}),
            "split/c2": ("none", ["S1#t2.c2", "S1#t2.r1.c2"], {}), "role/c3": ("none", ["S1#t2.c3", "S1#t2.r1.c3"], {}),
            "relation/c1>c2": ("none", ["S1#t2.c1", "S1#t2.c2", "S1#t2.r1.c1"], {}),
            "relation/c1>c3": ("none", ["S1#t2.c1", "S1#t2.c3", "S1#t2.r1.c1"], {}),
            "relation/c2>c3": ("none", ["S1#t2.c2", "S1#t2.c3", "S1#t2.r1.c2"], {}),
        }
        title_relations = [("S1#t1.c1", "has_stage:as_stated", "S1#t1.r1.c1"), ("S1#t3.c1", "has_stage:as_stated", "S1#t3.r1.c1"),
                           ("S1#t4.c1", "has_stage:as_stated", "S1#t4.r1.c1"),
                           *((c, "has_team_2:as_stated", c.replace(".c", ".r1.c")) for c in TEAM_COLUMNS)]
        return {
            "S1#t1": (teams, [], []),
            "S1#t2": (venues, [], []),
            "S1#t3": fixture_table("S1#t3", False, t3_relation),
            "S1#t4": fixture_table("S1#t4", t4_exception),
            "S1#1": ({"heading_entity": ("tournament", ["S1#1"], {})}, title_relations, []),
            "S1#5": ({"heading_entity": ("none", ["S1#5"], {})}, [], []),
            "S1#14": ({"heading_entity": ("none", ["S1#14"], {})}, [], []),
            "S1#15": ({"heading_entity": ("none", ["S1#15"], {})}, [], []),
        }

    def element(self, element_id):
        return next(e for e in rd.skeleton(self.document, self.bundle_, self.index) if e.element_id == element_id)

    def element_reading(self, element_id, plan, *, not_a_table=None):
        if not_a_table:
            return ElementReading(element_id=element_id, status="not_a_table", not_a_table_reason=not_a_table[0],
                                  basis=self.basis(*not_a_table[1]))
        slots, relations, exceptions = plan[element_id]
        rid = rd.reading_id(element_id)
        return ElementReading(
            element_id=element_id,
            slots=[ReadingSlotAnswer(slot_id=f"{rid}/{short}", choice=choice, basis=self.basis(*ids), **extra)
                   for short, (choice, ids, extra) in slots.items()],
            section_relations=[ReadingSectionRelation(column_id=column, choice=choice, basis=self.basis(element_id, cell))
                               for column, choice, cell in relations],
            exceptions=exceptions,
        )

    def reading_responder(self, plan=None, *, override=None):
        plan = plan or self.table_plan()
        override = override or {}

        def respond(payload):
            return ReadingResult(readings=[override.get(e["element_id"]) or self.element_reading(e["element_id"], plan)
                                           for e in payload["elements"]])
        return respond

    def readings(self, plan=None, **kwargs):
        """The validated Readings for the whole flyer (no provider)."""

        plan = plan or self.table_plan(**kwargs)
        elements = {e.element_id: e for e in rd.skeleton(self.document, self.bundle_, self.index)}
        result = ReadingResult(readings=[self.element_reading(e, plan) for e in elements])
        answered = rd.apply_result(result, elements, self.document, self.bundle_, self.index, final=False)
        self.assertEqual(answered.issues, [], [i.message for i in answered.issues])
        return answered.readings

    # -- the prose half -----------------------------------------------------------------

    def prose_claims(self):
        """What a perfect prose extraction states: the stages the format list
        names that no table does, belonging to the tournament the title names."""

        title = cite("S1#1", TITLE)
        return [ent("T", TITLE, "tournament", "S1#1"),
                ent("SF", "Semi-finals", "stage", "S1#9"), ent("FI", "Final", "stage", "S1#10"),
                rel("HS_SF", "T", "has stage", "SF", "has_stage", [title, cite("S1#9", self.text("S1#9"))], support="structural"),
                rel("HS_FI", "T", "has stage", "FI", "has_stage", [title, cite("S1#10", self.text("S1#10"))], support="structural")]

    def prose_extraction(self, payload):
        from ai.tests.support import extraction
        return extraction(self.frame(), *self.prose_claims())

    def analyse_readings(self, readings, *, items=(), pins=None):
        rs = ReconcileState(frame=self.frame(), graph=EvidenceGraph(), evidence_mode="readings", readings=readings,
                            pins=dict(pins or {}))
        for item in items:
            rs.graph = rs.graph.appended(EvidenceGraph(**{"entities" if hasattr(item, "eid") else "assertions": [item]}))
        rs.prose_scope = rd.prose_eligible(self.document, readings)
        rs.locked_segments = rd.locked_segments(self.document, readings)
        self.rs = rs
        return run_analysis(rs, index=self.index, bundle=self.bundle_)


def dismiss_everything(payload):
    return ExtractionResult(dismissed_segments=[{"segment_id": e["segment"]["segment_id"], "reason": "Not about the request."}
                                                for e in payload["uncovered_segments"]])


def no_claims(payload):
    return ProbeResult()


def undecidable_answers(payload):
    from ai.services.reconcile.responses import AdjudicationAnswer, AdjudicationResult
    return AdjudicationResult(answers=[AdjudicationAnswer(question_id=x["question_id"], option_id="undecidable") for x in payload["questions"]])


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings", AI_TRACE_DIR=None)
class ReadingsWorkflowTests(ReadingFixture):

    def responders(self, **overrides):
        defaults = dict(reading=self.reading_responder(), extraction=self.prose_extraction, extraction_correction=dismiss_everything,
                        gap_probe=nothing_stated, gap_probe_correction=no_claims, adjudication=undecidable_answers,
                        verification=lambda payload: approve())
        return Responders(**{**defaults, **overrides})

    def run_flyer(self, provider):
        return run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=INTENT,
                                assets=self.assets, provider=provider)

    def test_the_ideal_reading_reaches_the_reference_outcome(self):
        provider = self.responders()
        result = self.run_flyer(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "partial")
        assert_reference(self, outcome_from_proposal(result.proposal_id, result.blocked_targets), load_spec("international_flyer"))
        # Reading -> prose extraction -> review; no table row was ever re-read by an AI.
        self.assertEqual(provider.requested[:3], ["reading", "reading", "extraction"])
        self.assertNotIn("extraction_correction", [s for s in provider.requested if s == "reading"])

    def test_prose_extraction_never_sees_structured_content(self):
        provider = self.responders()
        self.run_flyer(provider)

        structured = {s.segment_id for s in self.bundle_.segments() if s.kind in ("table", "table_row")}
        for stage in ("extraction", "extraction_correction", "gap_probe"):
            for payload in provider.payloads_for(stage):
                shown = {s["segment_id"] for s in payload.get("segments", [])}
                shown |= {e["segment"]["segment_id"] for e in payload.get("uncovered_segments", [])}
                self.assertFalse(shown & structured, f"{stage} was shown {sorted(shown & structured)}")

    def test_reading_calls_scale_with_schemas_not_rows(self):
        provider = self.responders()
        self.run_flyer(provider)

        payloads = provider.payloads_for("reading")
        self.assertEqual(sum(len(p["elements"]) for p in payloads), 8)  # 4 tables + 4 headings above them
        self.assertTrue(all(len(e.get("rows", [])) <= 8 for p in payloads for e in p["elements"]))

    def test_one_objection_to_a_reading_slot_re_reads_every_row(self):
        from ai.tests.support import objection, reject

        reviews = iter([
            reject(objection("decision", "read:rd/S1#t3/relation/c2>c3", "wrong_mapping",
                             "The Venue column is where each listed match is played.", option_id="played_at:as_stated", excerpt="Venue")),
            approve(),
        ])
        provider = self.responders(reading=self.reading_responder(self.table_plan(t3_relation="none")),
                                   verification=lambda payload: next(reviews))
        result = self.run_flyer(provider)

        self.assertEqual(provider.requested.count("verification"), 2)
        self.assertNotIn("reading", provider.requested[provider.requested.index("verification"):])  # no re-reading by an AI
        assert_reference(self, outcome_from_proposal(result.proposal_id, result.blocked_targets), load_spec("international_flyer"))

    def test_an_invalid_reading_is_re_asked_once_then_settles(self):
        bad = ElementReading(element_id="S1#t3", slots=[])  # no slot answered
        calls = {"n": 0}
        good = self.reading_responder()

        def respond(payload):
            calls["n"] += 1
            if calls["n"] == 1:
                result = good(payload)
                result.readings = [bad if r.element_id == "S1#t3" else r for r in result.readings]
                return result
            return good(payload)

        provider = self.responders(reading=respond)
        result = self.run_flyer(provider)

        self.assertEqual(provider.requested[:3], ["reading", "reading", "reading"])
        self.assertEqual([e["element_id"] for e in provider.payloads_for("reading")[1]["elements"]], ["S1#t3"])
        assert_reference(self, outcome_from_proposal(result.proposal_id, result.blocked_targets), load_spec("international_flyer"))
