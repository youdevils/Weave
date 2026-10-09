"""
Reconcile's convergence resilience (ai/README.md, "Convergence"):

    Every newly produced, fixable piece of AI output gets one bounded
    correction opportunity, whatever earlier work in the run spent;
    Adjudication and Gap Probe continue while genuinely new work is
    discovered; the total provider budget and bounded no-progress rules are
    the termination controls, and recovery never spends the calls a
    Verification pass needs.

Generic fixtures, no domain strings: a chain of kinds each requiring the next
(site -> region -> country -> bloc -> council), whose layers only become
probe-able one at a time -- deeper than the old fixed round counts (2 probe
rounds, 3 adjudication rounds) could reach.
"""

import tempfile
from pathlib import Path
from unittest import mock

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from pydantic import BaseModel

from model.models.proposal import ProposalChange

from ai.services.execution import AIExecutionService
from ai.services.operation_definitions import build_reconcile_workflow
from ai.services.orchestrator import run_ai_operation
from ai.services.provider import AIProvider, ProviderResult
from ai.services.reconcile.responses import AdjudicationAnswer, AdjudicationResult, Citation, ProbeResult
from ai.services.reconcile.state import ReconcileState
from ai.services.result_schema import OperationOutcome
from ai.services.stages.reconcile_steps import affords_recovery, close_round, may_run_round, open_round, verification_pass_cost
from ai.services.tracing import load
from ai.services.workflow.engine import WorkflowDefinition, WorkflowRun, WorkflowState
from ai.tests.support import (
    AIServiceTestCase,
    approve,
    assertion,
    entity,
    extraction,
    frame,
    graph,
    objection,
    probe,
    reject,
    target,
    verdict,
)

TEXT = (
    "Sites\n\n"
    "North Depot is located in Highland Region.\n\n"
    "Highland Region is part of Freedonia.\n\n"
    "Freedonia is a member of the Northern Bloc.\n\n"
    "The Northern Bloc is governed by the Bloc Council.\n"
)
ASSETS = [{"name": "notes.txt", "content": TEXT, "mime_type": "text/plain"}]
INTENT = "Add the sites in these notes, with everything they need."

# (subject name, predicate, object name, object kind, the sentence stating it)
LAYERS = [
    ("North Depot", "is located in", "Highland Region", "region", "North Depot is located in Highland Region."),
    ("Highland Region", "is part of", "Freedonia", "country", "Highland Region is part of Freedonia."),
    ("Freedonia", "is a member of", "Northern Bloc", "bloc", "Freedonia is a member of the Northern Bloc."),
    ("Northern Bloc", "is governed by", "Bloc Council", "council", "The Northern Bloc is governed by the Bloc Council."),
]
CHAIN = {"North Depot", "Highland Region", "Freedonia", "Northern Bloc", "Bloc Council"}


class Responders(AIProvider):
    """A fake provider answering each stage with a responder (payload ->
    result), however often the workflow re-enters it -- for runs whose number
    and order of calls is what is under test. Records what was asked."""

    def __init__(self, **responders):
        self.responders = responders
        self.requested: list[str] = []
        self.payloads: list[dict] = []

    def payloads_for(self, stage) -> list[dict]:
        return [p for s, p in zip(self.requested, self.payloads) if s == stage]

    def generate_structured(self, *, system_prompt, user_payload, response_schema, config):
        stage = user_payload.get("stage")
        self.requested.append(stage)
        self.payloads.append(user_payload)
        if stage not in self.responders:
            raise AssertionError(f"No responder for stage {stage!r}.")
        output = self.responders[stage](user_payload)
        parsed = output if isinstance(output, BaseModel) else response_schema.model_validate(output)
        return ProviderResult(parsed=parsed, raw_text="", usage={}, provider="test")

    def explain(self, *, context, issues, config):
        return ProviderResult(parsed=None, raw_text="", usage={}, provider="test")


# -- responders ----------------------------------------------------------------------


def first_pass(payload):
    """Extraction finds the site and nothing it needs."""

    return extraction(frame([target("T1", "sites", "sites")]), entity("E1", "North Depot", "site", hint="site", excerpt="North Depot"))


def dismiss_uncovered(payload):
    return {"intent_frame": {}, "evidence": {}, "dismissed_segments": [
        {"segment_id": e["segment"]["segment_id"], "reason": "Says what other things need, not which sites there are."}
        for e in payload["uncovered_segments"]
    ]}


def layer_for(requirement):
    name = (requirement.get("entity") or {}).get("name")
    return next(((n, layer) for n, layer in enumerate(LAYERS, 1) if layer[0] == name), (None, None))


class Prober:
    """Each round recovers the next layer for every requirement it is asked
    about. `unanchored_rounds`: rounds whose relationship claims first cite a
    segment that doesn't state them (a fixable defect)."""

    def __init__(self, unanchored_rounds=()):
        self.round = 0
        self.unanchored_rounds = set(unanchored_rounds)

    def __call__(self, payload):
        self.round += 1
        claims, verdicts = [], []
        for requirement in payload["requirements"]:
            n, layer = layer_for(requirement)
            if layer is None:
                verdicts.append(verdict(requirement["requirement_id"], "not_stated", segments_reviewed=requirement["segment_ids"]))
                continue
            _, predicate, name, kind, sentence = layer
            excerpt = "Sites" if self.round in self.unanchored_rounds else sentence
            claims += [entity(f"N{n}", name, kind, excerpt=name), assertion(f"L{n}", requirement["entity"]["eid"], predicate, f"N{n}", excerpt=excerpt)]
            verdicts.append(verdict(requirement["requirement_id"], "found", claim_ids=[f"L{n}"], segments_reviewed=requirement["segment_ids"]))
        return probe(*claims, verdicts=verdicts)


def fix_claims(payload):
    """A probe correction citing the sentence each invalid relationship claim states."""

    assertions = []
    for entry in payload["invalid_claims"]:
        item = dict(entry["item"])
        layer = next(layer for layer in LAYERS if layer[1] == item.get("predicate"))
        item.update(support="explicit", provenance=[{"source_id": "S1", "excerpt": layer[4], "segment_id": None, "locator": None}])
        assertions.append(item)
    return {"claims": {"assertions": assertions}, "verdicts": []}


def oracle(payload):
    """Answers each question with its only substantive option, citing the segment its claims cite."""

    segments = {s["segment_id"]: s["text"] for s in payload["segments"]}
    answers = []
    for question in payload["questions"]:
        options = [o["option_id"] for o in question["options"] if o["option_id"] not in ("none", "undecidable")]
        sid = question["segment_ids"][0]
        answers.append(AdjudicationAnswer(question_id=question["question_id"], option_id=options[0],
                                          citations=[Citation(segment_id=sid, excerpt=segments[sid])]))
    return AdjudicationResult(answers=answers)


def misquoting_oracle(payload):
    """The right option, but a citation that is not in the segment."""

    result = oracle(payload)
    for answer in result.answers:
        answer.citations = [Citation(segment_id=answer.citations[0].segment_id, excerpt="nowhere in these notes")]
    return result


def responders(**overrides):
    defaults = dict(extraction=first_pass, extraction_correction=dismiss_uncovered, gap_probe=Prober(),
                    gap_probe_correction=fix_claims, adjudication=oracle, verification=lambda payload: approve())
    return Responders(**{**defaults, **overrides})


# -- fixture -------------------------------------------------------------------------


class DepthFixture(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model(name="Holdings", purpose="Track sites and what governs them.",
                                     scope="Sites, regions, countries, blocs and councils.", exclusions="")
        kinds = {key: self.make_object_type(self.model, key=key) for key in ("site", "region", "country", "bloc", "council")}
        for key, subject, obj in (("located_in", "site", "region"), ("part_of", "region", "country"),
                                  ("member_of", "country", "bloc"), ("governed_by", "bloc", "council")):
            self.make_rule(self.make_relationship_type(self.model, key=key), kinds[subject], kinds[obj], object_minimum=1)
        self.trace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.trace_dir.cleanup)
        tracing = override_settings(AI_TRACE_DIR=self.trace_dir.name)
        tracing.enable()
        self.addCleanup(tracing.disable)

    def run_reconcile(self, provider, assets=ASSETS):
        return run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=INTENT, assets=assets,
                                provider=provider)

    def created_names(self, result):
        return {c.after["name"] for c in ProposalChange.objects.filter(proposal_id=result.proposal_id)
                if c.target_type == "Object" and c.operation == "create"}

    def snapshots(self, result):
        return [s["snapshot"] for s in load(Path(self.trace_dir.name) / str(result.execution_id))
                if s["kind"] == "deterministic" and s["stage"] == "analysis"]

    def assert_bounded(self, result):
        self.assertLessEqual(result.provider_calls, settings.AI_WORKFLOW_MAX_PROVIDER_CALLS + settings.AI_TERMINAL_EXPLANATION_MAX_CALLS)


# -- D3: progress-driven convergence across dependency depth --------------------------


class DependencyDepthTests(DepthFixture):

    def test_convergence_follows_the_chain_past_the_old_fixed_round_counts(self):
        provider = responders()

        result = self.run_reconcile(provider)

        # Each layer is probed only once the one before it is decided: four
        # probe rounds (the old cap was 2), four adjudication rounds (was 3).
        self.assertEqual(provider.requested.count("gap_probe"), 4)
        self.assertEqual(provider.requested.count("adjudication"), 4)
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "complete")
        self.assertTrue(CHAIN <= self.created_names(result), self.created_names(result))
        self.assert_bounded(result)


# -- D1: one correction opportunity per unit of new work -------------------------------


class CorrectionPerRoundTests(DepthFixture):

    def test_each_probe_round_gets_its_own_correction(self):
        provider = responders(gap_probe=Prober(unanchored_rounds={1, 2}))

        result = self.run_reconcile(provider)

        # Round 1's correction no longer spends round 2's.
        self.assertEqual(result.stage_summary["gap_probe_correction"]["calls"], 2)
        rounds = [i for i, stage in enumerate(provider.requested) if stage == "gap_probe"]
        for index in rounds[:2]:
            self.assertEqual(provider.requested[index + 1], "gap_probe_correction")
        second = provider.payloads_for("gap_probe_correction")[1]
        self.assertEqual([e["issues"][0]["code"] for e in second["invalid_claims"]], ["unanchored_claim"])
        # The corrected claims entered the graph like any other.
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "complete")
        self.assertTrue(CHAIN <= self.created_names(result))
        self.assert_bounded(result)

    def test_a_claim_no_segment_could_anchor_skips_the_rounds_correction(self):
        prober = Prober(unanchored_rounds={1})

        def probing(payload):
            result = prober(payload)
            if prober.round == 1:
                # North Depot and Freedonia: no sentence names both, and the one
                # heading names neither -- nothing a correction could cite.
                site = payload["requirements"][0]["entity"]["eid"]
                result.claims.entities.append(entity("Q1", "Freedonia", "country", excerpt="Freedonia"))
                result.claims.assertions.append(assertion("Q2", site, "belongs to", "Q1", excerpt=LAYERS[0][4]))
            return result

        provider = responders(gap_probe=probing)

        result = self.run_reconcile(provider)

        first = provider.requested.index("gap_probe")
        self.assertEqual(provider.requested[first + 1], "gap_probe_correction")
        correction = provider.payloads_for("gap_probe_correction")[0]
        ingress = self.snapshots(result)[-1]["ingress"]
        q2 = next(e["id"] for e in ingress if e.get("local") == "Q2")
        # The anchored claim is corrected; the unanchorable one is not re-asked ...
        self.assertNotIn(q2, [e["id"] for e in correction["invalid_claims"]])
        self.assertTrue(correction["invalid_claims"])
        # ... and is dropped with its own reason, like any unrecovered claim.
        fate = [e for e in ingress if e["id"] == q2][-1]
        self.assertEqual(fate["outcome"], "dropped")
        self.assertIn("does not mention both", fate["reason"])
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertTrue(CHAIN <= self.created_names(result))

    def test_each_adjudication_round_gets_its_own_correction(self):
        rounds = {"n": 0}

        def adjudicator(payload):
            if payload["feedback"]:
                return oracle(payload)
            rounds["n"] += 1
            return misquoting_oracle(payload) if rounds["n"] <= 2 else oracle(payload)

        provider = responders(adjudication=adjudicator)

        result = self.run_reconcile(provider)

        self.assertEqual(result.stage_summary["adjudication_correction"]["calls"], 2)
        pins = self.snapshots(result)[-1]["pins"]
        self.assertTrue(pins)
        self.assertEqual({p["basis"] for p in pins.values()}, {"adjudicated"})
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertTrue(CHAIN <= self.created_names(result))
        self.assert_bounded(result)


class ExtractionWaveTests(DepthFixture):

    def test_claims_a_segment_re_ask_produces_get_their_own_wave(self):
        def extracting(payload):
            # An invalid claim; the added sentence naming the site is left
            # uncovered (re-asked once: a segment re-ask in the first wave).
            result = first_pass(payload)
            result.evidence.entities.append(entity("E2", "Highland Region", "region", excerpt="Highland Regoin"))
            return result

        waves = []

        def correcting(payload):
            waves.append(payload)
            if len(waves) == 1:
                # Wave 1: E2 fixed; the re-asked segment yields a new, unanchored claim.
                return {"intent_frame": {}, "evidence": graph(
                    entity("E2", "Highland Region", "region", excerpt="Highland Region"),
                    assertion("Q1", "E1", "is located in", "E2", excerpt="Sites"),
                ).model_dump(mode="json"), "dismissed_segments": []}
            # Wave 2: Q1 fixed; a brand-new invalid claim from a correction is not corrected again.
            return {"intent_frame": {}, "evidence": graph(
                assertion(waves[1]["invalid_items"][0]["id"], "E1", "is located in", "E2", excerpt=LAYERS[0][4]),
                entity("Q2", "Freedonia", "country", excerpt="Freedonai"),
            ).model_dump(mode="json"), "dismissed_segments": []}

        provider = responders(extraction=extracting, extraction_correction=correcting)

        result = self.run_reconcile(provider, assets=[{**ASSETS[0], "content": TEXT + "\nNorth Depot opened in 2019.\n"}])

        self.assertEqual(provider.requested[:3], ["extraction", "extraction_correction", "extraction_correction"])
        self.assertEqual(provider.requested.count("extraction_correction"), 2)
        first, second = waves
        self.assertEqual([e["id"] for e in first["invalid_items"]], ["E2"])
        self.assertTrue(first["uncovered_segments"])
        # The second wave re-asks only what the segment re-ask produced.
        self.assertEqual(len(second["invalid_items"]), 1)
        self.assertEqual(second["invalid_items"][0]["item"]["predicate"], "is located in")
        self.assertEqual(second["uncovered_segments"], [])
        fates = {}
        for entry in self.snapshots(result)[0]["ingress"]:
            fates[entry["id"]] = entry["outcome"]
        self.assertEqual(fates[second["invalid_items"][0]["id"]], "accepted")
        self.assertEqual(fates["Q2"], "dropped")
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertTrue(CHAIN <= self.created_names(result))
        self.assert_bounded(result)


# -- D2: a verdict's claim references are part of the response contract ----------------


class VerdictContractTests(DepthFixture):

    def site_requirement(self, provider):
        return provider.payloads_for("gap_probe")[0]["requirements"][0]["requirement_id"]

    def outcome_after_first_round(self, result, requirement_id):
        return next(s["probe_outcomes"][requirement_id] for s in self.snapshots(result) if requirement_id in s["probe_outcomes"])

    def broken_first(self, later):
        """Round 1: claims: [], verdict 'found' naming Z1. Later rounds: `later`."""

        calls = {"n": 0}

        def probing(payload):
            calls["n"] += 1
            if calls["n"] == 1:
                return probe(verdicts=[verdict(r["requirement_id"], "found", claim_ids=["Z1"]) for r in payload["requirements"]])
            return later(payload)

        return probing

    def test_a_verdict_naming_claims_it_never_emitted_is_re_asked(self):
        probing = self.broken_first(Prober())

        def correcting(payload):
            requirement = payload["invalid_verdicts"][0]["requirement"]
            _, predicate, name, kind, sentence = LAYERS[0]
            return probe(entity("N1", name, kind, excerpt=name), assertion("Z1", requirement["entity"]["eid"], predicate, "N1", excerpt=sentence),
                         verdicts=[verdict(requirement["requirement_id"], "found", claim_ids=["Z1"])])

        provider = responders(gap_probe=probing, gap_probe_correction=correcting)

        result = self.run_reconcile(provider)

        requirement_id = self.site_requirement(provider)
        correction = provider.payloads_for("gap_probe_correction")[0]
        self.assertEqual(correction["missing_verdicts"], [])
        [invalid] = correction["invalid_verdicts"]
        self.assertEqual(invalid["requirement"]["requirement_id"], requirement_id)
        self.assertEqual(invalid["previous_verdict"]["claim_ids"], ["Z1"])
        self.assertEqual(invalid["issues"][0]["code"], "verdict_claim_missing")
        self.assertIn("Z1", invalid["issues"][0]["message"])
        # Corrected: a finding, not an unsupported one and not an absence.
        self.assertEqual(self.outcome_after_first_round(result, requirement_id), "found")
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertTrue(CHAIN <= self.created_names(result))

    def test_a_verdict_may_name_claims_it_was_shown(self):
        prober = Prober()

        def probing(payload):
            result = prober(payload)
            if prober.round == 1:
                shown = {e["eid"] for e in payload["already_extracted"]["entities"]}
                self.assertIn("E1", shown)
                result.verdicts[0].claim_ids.append("E1")
            return result

        provider = responders(gap_probe=probing)

        result = self.run_reconcile(provider)

        self.assertNotIn("gap_probe_correction", provider.requested)
        self.assertEqual(self.outcome_after_first_round(result, self.site_requirement(provider)), "found")
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)

    def test_a_verdict_still_broken_after_its_correction_counts_as_unsupported(self):
        probing = self.broken_first(Prober())

        def still_broken(payload):
            return probe(verdicts=[verdict(e["requirement"]["requirement_id"], "found", claim_ids=["Z1"]) for e in payload["invalid_verdicts"]])

        provider = responders(gap_probe=probing, gap_probe_correction=still_broken)

        result = self.run_reconcile(provider)

        requirement_id = self.site_requirement(provider)
        # One correction for that round, never a second.
        self.assertEqual(provider.requested[provider.requested.index("gap_probe") + 1], "gap_probe_correction")
        self.assertEqual(provider.requested[provider.requested.index("gap_probe") + 2], "gap_probe")
        self.assertEqual(self.outcome_after_first_round(result, requirement_id), "found_unsupported")
        # ... which earns the one re-probe, told why.
        again = provider.payloads_for("gap_probe")[1]["requirements"][0]
        self.assertEqual(again["requirement_id"], requirement_id)
        self.assertIn("previous_answer", again)
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)


# -- D3: termination -----------------------------------------------------------------------


def unsupported(payload):
    """Always 'found', citing only a claim it was shown that relates nothing: no progress."""

    return probe(verdicts=[verdict(r["requirement_id"], "found", claim_ids=["E1"]) for r in payload["requirements"]])


class NoProgressTests(DepthFixture):

    def test_a_re_probe_without_progress_is_the_last_round(self):
        provider = responders(gap_probe=unsupported)

        result = self.run_reconcile(provider)

        # Round 1 (no progress) earns the one re-probe of that same work, which
        # makes no progress either: nothing is left to probe.
        self.assertEqual(provider.requested.count("gap_probe"), 2)
        self.assertEqual(self.snapshots(result)[-1]["idle_rounds"]["gap_probe"], 2)
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)

    @override_settings(AI_RECONCILE_GAP_PROBE_MAX_IDLE_ROUNDS=1)
    def test_rounds_without_progress_stop_at_the_idle_limit(self):
        provider = responders(gap_probe=unsupported)

        result = self.run_reconcile(provider)

        # The re-probe is work the class has already seen: no fresh streak.
        self.assertEqual(provider.requested.count("gap_probe"), 1)
        final = self.snapshots(result)[-1]
        self.assertEqual(final["idle_rounds"]["gap_probe"], 1)
        self.assertTrue(final["work_queue"]["deferred_evidence"])
        self.assertEqual(provider.requested[-1], "verification")
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)

    @override_settings(AI_RECONCILE_ADJUDICATION_MAX_IDLE_ROUNDS=0)
    def test_a_class_that_may_take_no_round_defers_without_defaulting(self):
        provider = responders()

        result = self.run_reconcile(provider)

        self.assertNotIn("adjudication", provider.requested)
        final = self.snapshots(result)[-1]
        self.assertTrue(final["work_queue"]["deferred_decisions"])
        self.assertEqual(final["pins"], {})
        ledger = {d["decision_id"]: d for d in provider.payloads_for("verification")[0]["decision_ledger"]}
        opened = [d for d in ledger.values() if d["decision_id"].startswith("open:")]
        self.assertTrue(opened)
        self.assertEqual({(d["outcome"], d["basis"]) for d in opened}, {("unadjudicated", "budget")})
        self.assertIsNone(result.proposal_id)


# -- the Verification reserve ------------------------------------------------------------------


class VerificationReserveTests(DepthFixture):

    # extraction + probe round 1 + adjudication round 1 = 3 of 5 calls: the
    # next probe round would leave 1, less than a full Verification pass (the
    # review + the re-ask of an unroutable objection).
    @override_settings(AI_WORKFLOW_MAX_PROVIDER_CALLS=5)
    def test_recovery_never_spends_a_verification_pass(self):
        reviews = []

        def reviewing(payload):
            reviews.append(payload)
            if len(reviews) == 1:
                return reject(objection("segment", "S1#2", "missed_evidence", "Something was missed."))  # unroutable: no evidence
            return approve()

        provider = responders(verification=reviewing)

        result = self.run_reconcile(provider)

        self.assertEqual(provider.requested, ["extraction", "gap_probe", "adjudication", "verification", "verification"])
        self.assertEqual(result.stage_summary["verification_correction"]["calls"], 1)
        self.assertEqual(reviews[1]["feedback"][0]["code"], "unroutable_objection")
        self.assertTrue(self.snapshots(result)[-1]["work_queue"]["deferred_evidence"])
        self.assertTrue(result.blocked_targets)
        self.assertNotIn("budget_exhausted", [i.code for i in result.unresolved_issues])

    # After a send-back, recovery is checked against the reserve again: the
    # re-review still has its calls.
    @override_settings(AI_WORKFLOW_MAX_PROVIDER_CALLS=8)
    def test_after_a_send_back_recovery_still_leaves_the_review_its_calls(self):
        _, predicate, name, kind, sentence = LAYERS[2]
        missed = objection("segment", "S1#4", "missed_evidence", "Freedonia's bloc was missed.", evidence=graph(
            entity("X1", name, kind, excerpt=name), assertion("X2", "N2", predicate, "X1", excerpt=sentence),
        ))
        reviews = []

        def reviewing(payload):
            reviews.append(payload)
            return reject(missed) if len(reviews) == 1 else approve()

        provider = responders(verification=reviewing)

        result = self.run_reconcile(provider)

        self.assertEqual(provider.requested[-2:], ["verification", "verification"])
        self.assertLessEqual(result.provider_calls, 8)
        self.assertNotIn("budget_exhausted", [i.code for i in result.unresolved_issues])


# -- the rules, unit by unit ----------------------------------------------------------------------


class _Stub(AIProvider):
    def generate_structured(self, **kwargs):
        return ProviderResult(parsed=ProbeResult(), raw_text="", usage={}, provider="test")

    def explain(self, **kwargs):
        return ProviderResult(parsed=None, raw_text="", usage={}, provider="test")


def make_run(definition=None, **counters):
    run = WorkflowRun(operation=None, model=None, user=None, intent=None, bundle=None, provider=_Stub(), config=None,
                      execution=None, definition=definition or build_reconcile_workflow(), state=WorkflowState(reconcile=ReconcileState()))
    for name, value in counters.items():
        setattr(run, name, value)
    return run


class ScopedBudgetTests(SimpleTestCase):
    """The engine's scopes: an opener is charged to its own key only, and opens
    a fresh correction scope before its output is evaluated."""

    def setUp(self):
        patcher = mock.patch.multiple(AIExecutionService, record_context_digest=mock.DEFAULT, accumulate_usage=mock.DEFAULT)
        patcher.start()
        self.addCleanup(patcher.stop)

    def call(self, run, stage, correction=False):
        run.call_provider(stage_id=stage, system_prompt="", payload={}, response_schema=ProbeResult, correction=correction)

    def definition(self, **budgets):
        return WorkflowDefinition(
            stages={}, first_stage="probe",
            stage_budgets={"probe": None, "probe_correction": 1, "extract": 4, "extract_correction": 2, **budgets},
            scoped_budgets={"probe_correction": "probe", "extract_correction": None},
            total_budget=10, explanation_budget=0,
        )

    def test_an_opener_opens_a_scope_it_is_never_charged_to(self):
        run = make_run(self.definition())

        self.call(run, "probe")

        self.assertEqual(run.stage_calls, {"probe": 1})
        self.assertEqual(run.scope_calls["probe_correction"], 0)
        self.assertTrue(run.allows("probe_correction"))

    def test_one_correction_per_scope_and_a_correction_never_reopens_it(self):
        run = make_run(self.definition())

        self.call(run, "probe")
        self.call(run, "probe_correction")

        self.assertFalse(run.allows("probe_correction"))
        self.call(run, "probe")  # the next round
        self.assertTrue(run.allows("probe_correction"))
        self.assertEqual((run.stage_calls["probe"], run.stage_calls["probe_correction"]), (2, 1))

    def test_a_correct_re_ask_is_charged_to_its_scope(self):
        definition = self.definition(adjudication=None, adjudication_correction=1)
        definition.scoped_budgets["adjudication_correction"] = "adjudication"
        run = make_run(definition)

        self.call(run, "adjudication")
        self.assertTrue(run.allows("adjudication", correction=True))
        self.call(run, "adjudication", correction=True)

        self.assertFalse(run.allows("adjudication", correction=True))
        self.assertEqual(run.stage_calls, {"adjudication": 1, "adjudication_correction": 1})

    def test_a_stage_opened_scope(self):
        run = make_run(self.definition())

        self.assertTrue(run.allows("extract_correction"))  # never opened: a fresh scope
        self.call(run, "extract_correction")
        self.call(run, "extract_correction")
        self.assertFalse(run.allows("extract_correction"))
        run.open_scope("extract_correction")
        self.assertTrue(run.allows("extract_correction"))

    def test_an_uncapped_stage_is_bounded_by_the_total_only(self):
        run = make_run(self.definition(), workflow_calls=9)

        self.assertTrue(run.allows("probe"))
        self.assertEqual(run.remaining_calls(), 1)
        run.workflow_calls = 10
        self.assertFalse(run.allows("probe"))


class RoundRuleTests(SimpleTestCase):

    def test_new_work_starts_a_fresh_idle_streak(self):
        for stage in ("adjudication", "gap_probe"):
            run = make_run()
            rs = run.state.reconcile
            rs.idle_rounds[stage], rs.routed_work[stage] = 2, {"w1"}

            self.assertTrue(may_run_round(run, stage, ["w1", "w2"]), stage)
            self.assertEqual(rs.idle_rounds[stage], 0)

    def test_work_already_routed_does_not(self):
        for stage in ("adjudication", "gap_probe"):
            run = make_run()
            rs = run.state.reconcile
            rs.idle_rounds[stage], rs.routed_work[stage] = 2, {"w1"}

            self.assertFalse(may_run_round(run, stage, ["w1"]), stage)
            self.assertEqual(rs.idle_rounds[stage], 2)

    def test_a_round_without_progress_extends_the_streak(self):
        rs = ReconcileState()

        open_round(rs, "gap_probe", ["r1"])
        rs.graph = graph(entity("E1", "North Depot", "site"))
        close_round(rs)
        self.assertEqual(rs.idle_rounds["gap_probe"], 0)
        open_round(rs, "gap_probe", ["r2"])
        close_round(rs)
        self.assertEqual(rs.idle_rounds["gap_probe"], 1)
        self.assertEqual(rs.routed_work["gap_probe"], {"r1", "r2"})
        self.assertIsNone(rs.round_open)

    def test_recovery_always_leaves_a_full_verification_pass(self):
        total = settings.AI_WORKFLOW_MAX_PROVIDER_CALLS
        run = make_run(workflow_calls=total - 3)
        self.assertEqual(verification_pass_cost(run), 2)
        self.assertTrue(affords_recovery(run))
        run.workflow_calls = total - 2
        self.assertFalse(affords_recovery(run))
        # Its correction already spent, a pass needs only the review.
        run.stage_calls["verification_correction"] = 1
        self.assertEqual(verification_pass_cost(run), 1)
        self.assertTrue(affords_recovery(run))
