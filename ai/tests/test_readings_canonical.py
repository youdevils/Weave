"""
The Phase 5 gate's hard tier (.Documentation/reconcile-architecture-plan.md):
every canonical regression document passes its reference spec in a SCRIPTED
readings-mode run -- the ideal Reading of its structure and the ideal
extraction of its prose, everything else OnyxJar. (The flyer PDF's run is
ai.tests.test_readings.ReadingsWorkflowTests.)
"""

from django.test import override_settings

from ai.services.orchestrator import run_ai_operation
from ai.services.reconcile import readings as rd
from ai.services.reconcile.responses import DemCitation, ElementReading, ReadingResult, ReadingSlotAnswer
from ai.services.result_schema import OperationOutcome
from ai.tests.reference import assert_reference, load_spec, outcome_from_proposal
from ai.tests.rugby import FLYER_ASSETS, INTENT as RUGBY_INTENT, RugbyFixture
from ai.tests.support import approve, assertion, entity, extraction, fact, frame, nothing_stated, target
from ai.tests.test_readings import dismiss_everything, no_claims, undecidable_answers
from ai.tests.test_reconcile_resilience import ASSETS as DEPTH_ASSETS, INTENT as DEPTH_INTENT, LAYERS, DepthFixture, Responders
from ai.tests.test_reference_specs import REPORT_ASSETS, InternationalReportSpecTests
from ai.tests.test_governance_contract import INTENT as FLYER_INTENT


def run(testcase, *, model, intent, assets, reading=None, extraction_result):
    provider = Responders(
        reading=reading or (lambda payload: ReadingResult()), extraction=lambda payload: extraction_result,
        extraction_correction=dismiss_everything, gap_probe=nothing_stated, gap_probe_correction=no_claims,
        adjudication=undecidable_answers, verification=lambda payload: approve(),
    )
    result = run_ai_operation(operation_id="reconcile", model=model, user=testcase.user, intent_text=intent, assets=assets, provider=provider)
    return provider, result


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings", AI_TRACE_DIR=None)
class ReportTests(InternationalReportSpecTests):
    """Prose only: no structure to read -- Reading costs no call."""

    def test_the_prose_report_passes_its_spec(self):
        provider, result = run(self, model=self.model, intent=FLYER_INTENT, assets=self.assets,
                               extraction_result=extraction(self.frame(), *self.ideal_report_items()))

        self.assertNotIn("reading", provider.requested)
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        assert_reference(self, outcome_from_proposal(result.proposal_id, result.blocked_targets), load_spec("international_report"))


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings", AI_TRACE_DIR=None)
class DepthChainTests(DepthFixture):

    def test_the_depth_chain_passes_its_spec(self):
        kinds = {"North Depot": "site", **{name: kind for _, _, name, kind, _ in LAYERS}}
        ids = {name: f"E{n}" for n, name in enumerate(kinds, 1)}
        keys = ("located_in", "part_of", "member_of", "governed_by")
        items = [entity(ids[name], name, kind, hint=kind, excerpt=name) for name, kind in kinds.items()]
        items += [assertion(f"A{n}", ids[subject], predicate, ids[obj], hint=key, excerpt=sentence)
                  for n, ((subject, predicate, obj, _, sentence), key) in enumerate(zip(LAYERS, keys), 1)]
        provider, result = run(self, model=self.model, intent=DEPTH_INTENT, assets=DEPTH_ASSETS,
                               extraction_result=extraction(frame([target("T1", "sites", "sites", hint="site")]), *items))

        self.assertNotIn("reading", provider.requested)
        assert_reference(self, outcome_from_proposal(result.proposal_id, result.blocked_targets), load_spec("depth_chain"))


@override_settings(AI_RECONCILE_EVIDENCE_MODE="readings", AI_TRACE_DIR=None)
class RugbyFlyerTests(RugbyFixture):
    """The small flyer: its venue table is Read; its prose is extracted."""

    def reading(self, payload):
        from ai.services.evidence_bundle import EvidenceBundle

        bundle = EvidenceBundle.from_assets(FLYER_ASSETS)
        document = bundle.document()

        def basis(*ids):
            return [DemCitation(dem_id=d, excerpt=rd.dem_text(d, document, bundle)) for d in ids]

        plan = {
            "S1#t1": {"role/c1": ("venue", ["S1#t1.c1", "S1#t1.r1.c1"]), "role/c2": ("value", ["S1#t1.c2", "S1#t1.r1.c2"]),
                      "role/c3": ("none", ["S1#t1.c3", "S1#t1.r1.c3"]),
                      "relation/c1>c2": ("none", ["S1#t1.c1", "S1#t1.r1.c1"]), "relation/c1>c3": ("none", ["S1#t1.c1", "S1#t1.r1.c1"]),
                      "relation/c2>c3": ("none", ["S1#t1.c2", "S1#t1.r1.c2"])},
            "S1#1": {"heading_entity": ("none", ["S1#1"])},
            "S1#3": {"heading_entity": ("none", ["S1#3"])},
        }
        return ReadingResult(readings=[
            ElementReading(element_id=e["element_id"], slots=[
                ReadingSlotAnswer(slot_id=f"{rd.reading_id(e['element_id'])}/{short}", choice=choice, basis=basis(*ids))
                for short, (choice, ids) in plan[e["element_id"]].items()])
            for e in payload["elements"]])

    def prose_items(self):
        """flyer_items, minus what only the table states (the Reading reads it)."""

        s2 = "Match 1: New Zealand v Fiji, played at Eden Park"
        return [
            entity("E1", "2027 Championship", "championship", hint="tournament", excerpt="2027 Championship", source_id="intent"),
            entity("E2", "Pool Stage", "stage", hint="stage", excerpt="Pool Stage"),
            entity("E3", "Match 1", "match", hint="match", excerpt="Match 1: New Zealand v Fiji"),
            entity("E4", "New Zealand", "team", hint="team", excerpt="New Zealand v Fiji"),
            entity("E5", "Fiji", "team", hint="team", excerpt="New Zealand v Fiji"),
            entity("E6", "Eden Park", "venue", hint="venue", excerpt=s2),
            assertion("A1", "E1", "includes stage", "E2", hint="has_stage", support="structural",
                      spans=[("stages listed in the flyer to the 2027 Championship", "intent"), ("Pool Stage", "S1")]),
            assertion("A2", "E2", "includes", "E3", hint="has_match", excerpt="Pool Stage"),
            assertion("A3", "E3", "is played by", "E4", hint="has_team", excerpt="Match 1: New Zealand v Fiji"),
            assertion("A4", "E3", "is played by", "E5", hint="has_team", excerpt="Match 1: New Zealand v Fiji"),
            assertion("A5", "E3", "played at", "E6", hint="played_at", excerpt="played at Eden Park"),
            fact("F2", "E6", "Capacity", "50000", excerpt="Eden Park capacity: 50000"),
        ]

    def test_the_rugby_flyer_passes_its_spec(self):
        provider, result = run(self, model=self.model, intent=RUGBY_INTENT, assets=FLYER_ASSETS, reading=self.reading,
                               extraction_result=extraction(self.flyer_frame(), *self.prose_items()))

        self.assertEqual(provider.requested[:2], ["reading", "extraction"])
        assert_reference(self, outcome_from_proposal(result.proposal_id, result.blocked_targets), load_spec("rugby_flyer"))


# -- tier 2: readings mode against the REPLAYED claims-mode baselines ----------------------

from ai.tests import test_trace_equivalence as te  # noqa: E402
from ai.tests.reference import evaluate  # noqa: E402


class ReplayedClaimsComparisonTests(te.FlyerReplayCase):
    """Deterministic, so gating: readings mode must pass every flyer spec
    assertion that any captured claims-mode run (replayed) passes -- on the
    same model, the one those runs were captured against."""

    def readings_outcome(self):
        from ai.tests.test_readings import ReadingFixture

        helper = ReadingFixture("setUp")
        helper.model, helper.user = self.model, self.user
        helper.assets = self.assets
        from ai.services.evidence_bundle import EvidenceBundle
        from ai.services.semantic.index import SemanticModelIndex

        helper.bundle_ = EvidenceBundle.from_assets(self.assets)
        helper.document = helper.bundle_.document()
        helper.index = SemanticModelIndex.load(self.model)
        provider = Responders(reading=helper.reading_responder(), extraction=helper.prose_extraction,
                              extraction_correction=dismiss_everything, gap_probe=nothing_stated, gap_probe_correction=no_claims,
                              adjudication=undecidable_answers, verification=lambda payload: approve())
        with override_settings(AI_RECONCILE_EVIDENCE_MODE="readings"):
            result = run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=FLYER_INTENT,
                                      assets=self.assets, provider=provider)
        return outcome_from_proposal(result.proposal_id, result.blocked_targets)

    def test_readings_pass_everything_the_replayed_claims_runs_pass(self):
        spec = load_spec("international_flyer")
        claims_passed, claims_results = set(), {}
        for run in te.RUNS:
            _, result = self.replay(run)
            checks = evaluate(outcome_from_proposal(result.proposal_id, result.blocked_targets), spec)
            claims_results[run] = sum(c.passed for c in checks)
            claims_passed |= {c.id for c in checks if c.passed}
        readings = {c.id: c for c in evaluate(self.readings_outcome(), spec)}

        print(f"\nflyer spec assertions passed -- claims replays: {claims_results}, readings: "
              f"{sum(c.passed for c in readings.values())}/{len(readings)}")
        self.assertEqual(sorted(i for i in claims_passed if not readings[i].passed), [],
                         {i: readings[i].detail for i in claims_passed if not readings[i].passed})
        # The expected improvement: what no claims-mode run achieved.
        positives = [c for c in readings.values() if c.id.split(":")[0] in ("tournament", "stage", "match", "team", "venue",
                                                                             "has_stage", "has_match", "played_at", "has_team", "has_team_2")]
        self.assertTrue(all(c.passed for c in positives), [c for c in positives if not c.passed])
