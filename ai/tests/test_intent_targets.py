"""
Explicit intent targets are requested work (ai/README.md, "Intent targets
are work"): every target ends in a reported status, and failing to find
evidence for one creates recoverable work -- a target gap for the Gap Probe
-- never a silent no-op.

    framing    the intent is the authority for what was asked: a target's
               excerpt is a verbatim span of the intent (elided quotes are
               literally repaired to their covering span; several targets may
               share one span) that names it; one that still fails is kept as
               unframed work, reported, and recoverable by Verification
    status     evidenced | folded (relationships in general) | retire |
               unframed | unmapped | undecided | not_evidenced (the last four
               are blocks: never NO_CHANGE_REQUIRED)
    gaps       a mapped target with nothing evidenced, or with relevant
               segments nothing accounted for, is probed at the level of its
               kind
"""

from pathlib import Path

from django.test import SimpleTestCase

from ai.services.intent_frame import covering_span, repair_elisions, validate_intent_frame
from ai.services.intent_frame import FrameAmendment
from ai.services.result_schema import OperationOutcome
from ai.services.tracing import ReplayProvider
from ai.tests.support import (
    AIServiceTestCase,
    ScriptedProvider,
    approve,
    assertion,
    entity,
    extraction,
    frame,
    nothing_stated,
    objection,
    probe,
    reject,
    target,
    verdict,
)
from ai.tests.rugby import INTENT
from ai.tests.test_evidence_lifecycle import InternationalFlyerFixture
from ai.tests.test_reconcile_convergence import single_option_oracle
from ai.tests.test_reconcile_workflow import ReconcileWorkflowTestCase

LIVE_TRACE = Path(__file__).parent / "fixtures" / "traces" / "international_flyer_live2"
LIVE_INTENT = ("I want add the venues and stages listed in the flyer to my model, create any relationships that should be "
               "associated as well based on the information available")


class FramingContractTests(SimpleTestCase):

    def test_an_elided_excerpt_is_repaired_to_its_covering_intent_span(self):
        self.assertEqual(covering_span("add the venues ... listed in the flyer", LIVE_INTENT), "add the venues and stages listed in the flyer")
        self.assertEqual(covering_span("add the ... stages listed in the flyer", LIVE_INTENT), "add the venues and stages listed in the flyer")
        # Fragments the intent does not contain, in order, are never "repaired".
        self.assertIsNone(covering_span("add the venues ... in the brochure", LIVE_INTENT))
        self.assertIsNone(covering_span("listed in the flyer ... add the venues", LIVE_INTENT))

    def test_two_targets_may_share_one_span_and_each_must_be_named_by_it(self):
        shared = "add the venues and stages listed in the flyer"
        framed = frame([target("T1", "venues", shared), target("T2", "stages", shared), target("T3", "matches", shared)])

        issues = validate_intent_frame(framed, LIVE_INTENT)

        self.assertEqual([(i.item_id, i.code) for i in issues], [("T3", "unanchored_claim")])

    def test_repair_records_the_original_and_validation_then_passes(self):
        framed = frame([target("T1", "venues", "add the venues ... listed in the flyer"),
                        target("T2", "stages", "add the ... stages listed in the flyer")])

        repaired, originals = repair_elisions(framed, LIVE_INTENT)

        self.assertEqual(validate_intent_frame(repaired, LIVE_INTENT), [])
        self.assertEqual(originals, {"T1": "add the venues ... listed in the flyer", "T2": "add the ... stages listed in the flyer"})


class RugbyTargetTests(ReconcileWorkflowTestCase):

    def stages_only(self):
        """Extraction found the stage but none of the requested venues."""

        items = [i for i in self.flyer_items(include_fiji=False, include_forsyth_barr=False)
                 if getattr(i, "eid", "") in ("E1", "E2") or getattr(i, "aid", "") == "A1"]
        return extraction(self.flyer_frame(), *items)

    def venue_probe(self, payload):
        venues = probe(
            entity("V1", "Eden Park", "venue", excerpt="Eden Park | Auckland"),
            entity("V2", "Forsyth Barr Stadium", "venue", excerpt="Forsyth Barr Stadium | Dunedin"),
            verdicts=[verdict(r["requirement_id"], "found", claim_ids=["V1", "V2"]) if r["requirement_id"] == "target:T1"
                      else verdict(r["requirement_id"], "not_stated") for r in payload["requirements"]],
        )
        return venues

    def test_a_target_extraction_missed_is_still_probed_and_recovered(self):
        provider = ScriptedProvider([self.stages_only(), extraction(frame()), self.venue_probe, approve()])

        result = self.run_reconcile(provider)

        # 1. Requested venues, none extracted (even after the re-ask): a target gap, probed at the level of the kind.
        self.assertEqual(provider.stages, ["extraction", "extraction_correction", "gap_probe", "verification"])
        sent = next(r for r in provider.payloads_for("gap_probe")[0]["requirements"] if r["requirement_id"] == "target:T1")
        self.assertIn("'venues'", sent["question"])
        self.assertTrue({"S1#t1", "S1#t1.r1", "S1#t1.r2"} <= set(sent["segment_ids"]))  # rows under a "Venue" header
        self.assertNotIn("'venue'", str(sent))  # catalogue names only, never type keys
        self.assertNotIn("_target", sent)
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertTrue({"Eden Park", "Forsyth Barr Stadium"} <= set(self.created_names(result)))

    def test_an_unmappable_target_is_reported_and_never_empties_the_others(self):
        intent = INTENT + " Also add the widgets."
        framed = frame([target("T1", "venues", "the venues"), target("T2", "widgets", "the widgets")])
        provider = ScriptedProvider([extraction(framed, *self.flyer_items()), approve()])

        result = self.run_reconcile(provider, intent=intent)

        # 4. Unmapped: a block of its own, never fabricated into a type; venues still reconcile.
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "partial")
        self.assertIn("Eden Park", self.created_names(result))
        self.assertEqual([(b["target"], b["reason"]) for b in result.blocked_targets], [("widgets", "unmapped")])
        self.assertTrue(any("model has no kind of entity or relationship for 'widgets'" in m for m in self.messages(result)))

    def test_relationships_in_general_fold_into_include_related(self):
        framed = frame([target("T1", "venues", "venues"), target("T2", "stages", "stages"),
                        target("T3", "relationships", "create any relationships that should be associated")])
        provider = ScriptedProvider([extraction(framed, *self.flyer_items()), approve()])

        result = self.run_reconcile(provider)

        statuses = {t["target_id"]: t["status"] for t in provider.payloads_for("verification")[0]["intent_targets"]}
        self.assertEqual(statuses, {"T1": "evidenced", "T2": "evidenced", "T3": "folded"})
        self.assertEqual(result.completeness, "complete")
        ledger = {d["decision_id"]: d for d in provider.payloads_for("verification")[0]["decision_ledger"]}
        self.assertEqual(ledger["target:T3"]["outcome"], "general_relationships")

    def test_elided_target_excerpts_are_repaired_not_dropped(self):
        intent = "Add the venues and stages listed in the flyer to the 2027 Championship."
        framed = self.flyer_frame()
        framed.targets = [target("T1", "venues", "Add the venues ... listed in the flyer"),
                          target("T2", "stages", "Add the ... stages listed in the flyer")]
        framed.include_related = False
        provider = ScriptedProvider([extraction(framed, *self.flyer_items()), approve()])

        result = self.run_reconcile(provider, intent=intent)

        # 5. No re-ask, no lost target.
        self.assertEqual(provider.stages, ["extraction", "verification"])
        ledger = {d["decision_id"]: d for d in provider.payloads_for("verification")[0]["decision_ledger"]}
        self.assertEqual(ledger["frame:T1"]["excerpts"], ["Add the venues and stages listed in the flyer"])
        self.assertEqual(ledger["frame:T1"]["detail"], {"repaired_from": "Add the venues ... listed in the flyer"})
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)

    def test_an_ungroundable_target_is_unframed_work_that_verification_can_restore(self):
        framed = self.flyer_frame()
        framed.targets = [target("T1", "venues", "the arenas"), target("T2", "stages", "stages")]
        restore = objection("intent", "intent", "frame_error", "The request asks for the venues too.",
                            frame_amendment=FrameAmendment(add_targets=[target("T1", "venues", "venues")]))
        provider = ScriptedProvider([
            extraction(framed, *self.flyer_items()), extraction(framed), reject(restore), approve(),
        ])

        result = self.run_reconcile(provider)

        # 5. Failed twice: kept as unframed work, shown to the reviewer, restored, reconciled.
        self.assertEqual(provider.stages, ["extraction", "extraction_correction", "verification", "verification"])
        first_review = provider.payloads_for("verification")[0]
        self.assertIn(("T1", "unframed"), [(t["target_id"], t["status"]) for t in first_review["intent_targets"]])
        self.assertIn("T1", [b.get("target_id") for b in first_review["blocked_targets"]])
        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.completeness, "complete")
        self.assertIn("Forsyth Barr Stadium", self.created_names(result))

    def test_a_target_already_satisfied_by_the_model_is_a_genuine_no_op(self):
        intent = "Add the venues listed in the notes."
        provider = ScriptedProvider([
            extraction(frame([target("T1", "venues", "the venues")]), entity("E1", "Qualifier Venue", "venue", hint="venue", excerpt="Qualifier Venue")),
            approve(),
        ])
        assets = [{"name": "notes.txt", "content": "Qualifier Venue hosted the qualifiers."}]

        result = self.run_reconcile(provider, intent=intent, assets=assets)

        # 6. The requested venue exists already: nothing to do, honestly.
        self.assertEqual(result.outcome, OperationOutcome.NO_CHANGE_REQUIRED)
        self.assertEqual(provider.payloads_for("verification")[0]["intent_targets"][0]["status"], "evidenced")


class AbsentEvidenceTests(AIServiceTestCase):

    INTENT = "Add the applications mentioned in this document."

    def setUp(self):
        self.model = self.make_model(name="Estate")
        self.make_object_type(self.model, key="application")
        self.server = self.make_object_type(self.model, key="server")
        self.hosts = self.make_relationship_type(self.model, key="runs_on")

    def run_reconcile(self, provider, text, intent=None):
        from ai.services.orchestrator import run_ai_operation

        return run_ai_operation(operation_id="reconcile", model=self.model, user=self.user, intent_text=intent or self.INTENT,
                                assets=[{"name": "doc.txt", "content": text}], provider=provider)

    def test_a_target_the_evidence_never_names_is_unresolved_not_a_no_op(self):
        provider = ScriptedProvider([
            extraction(frame([target("T1", "applications", "applications mentioned")])), nothing_stated, approve(),
        ])

        result = self.run_reconcile(provider, "Quarterly report.\n\nRevenue grew by four percent.")

        # 2. Nothing labelled as an application: the whole (bounded) document is probed for one.
        self.assertEqual(provider.stages, ["extraction", "gap_probe", "verification"])
        sent = provider.payloads_for("gap_probe")[0]["requirements"][0]
        self.assertEqual(sent["requirement_id"], "target:T1")
        # 7. Approved, yet requested work was not done: never NO_CHANGE_REQUIRED.
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertEqual([(b["target"], b["reason"], b["coverage"]) for b in result.blocked_targets],
                         [("applications", "not_evidenced", "complete")])
        self.assertTrue(any("the request asks to add 'applications', but the evidence names none." in f.message for f in result.findings))
        # 8. The reviewer was told.
        self.assertEqual(provider.payloads_for("verification")[0]["intent_targets"][0]["status"], "not_evidenced")

    def test_a_relationship_target_nothing_states_is_probed_then_reported(self):
        intent = "Link each application to the server it runs on."
        provider = ScriptedProvider([
            extraction(frame([target("T1", "runs on", "runs on", verb="link")]),
                       entity("E1", "Payroll", "application", hint="application", excerpt="Payroll"),
                       entity("E2", "Atlas", "server", hint="server", excerpt="Atlas")),
            nothing_stated, approve(),
        ])

        result = self.run_reconcile(provider, "Payroll and Atlas are listed in the inventory.", intent=intent)

        # 3. A relationship target with no relationship evidenced: a gap, then an honest block.
        sent = provider.payloads_for("gap_probe")[0]["requirements"][0]
        self.assertEqual((sent["requirement_id"], sent["looking_for"]["relationship"]), ("target:T1", "Runs On"))
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertEqual([(b["target"], b["reason"]) for b in result.blocked_targets], [("runs on", "not_evidenced")])


def no_claims(payload):
    return {"claims": {}, "verdicts": [{"requirement_id": r["requirement_id"], "status": "not_stated"} for r in payload["requirements"]]}


class LiveNoOpRegressionTests(InternationalFlyerFixture):
    """The live run that ended NO_CHANGE_REQUIRED (`international_flyer_live2`):
    T1/T2 elided, T3 'relationships', fixture rows ignored by Extraction and
    its correction. Replayed by stage; a stand-in answers the probe the
    corrected routing now asks for."""

    def test_the_request_survives_and_drives_the_search(self):
        provider = ReplayProvider(LIVE_TRACE, inject={"adjudication": [single_option_oracle] * 3, "gap_probe": [no_claims] * 2,
                                                      "gap_probe_correction": [no_claims]})

        result = self.run_reconcile(provider)

        # The run no longer stops after extraction: it decides what it can and searches.
        self.assertEqual(provider.requested[:2], ["extraction", "extraction_correction"])
        self.assertIn("gap_probe", provider.requested)
        self.assertEqual(provider.requested[-1], "verification")
        probed = {r["requirement_id"]: r for r in provider.payloads[provider.requested.index("gap_probe")]["requirements"]}
        # The venues target's gap is the fixture rows nothing accounted for.
        fixture_rows = {self.seg("Pool A | New Zealand v Fiji"), self.seg("Pool B | South Africa v Tonga")}
        self.assertTrue(fixture_rows <= set(probed["target:T1"]["segment_ids"]))
        self.assertTrue(any(rid.startswith("req:") for rid in probed))  # the stages' own requirements too
        verification = provider.payloads[provider.requested.index("verification")]
        self.assertEqual({t["target_id"]: t["status"] for t in verification["intent_targets"]},
                         {"T1": "evidenced", "T2": "evidenced", "T3": "folded"})
        # Nothing could be added, and that is reported -- never a successful no-op.
        self.assertNotEqual(result.outcome, OperationOutcome.NO_CHANGE_REQUIRED)
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertTrue(result.blocked_targets)
