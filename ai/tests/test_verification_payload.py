"""
The Verification payload shows each fact once
(ai.services.stages.verification.verification_ledger / _restated): every
record it leaves out of the ledger or the notes is (1) not a target
`VerificationStage.route()` can act on, (2) present in the same payload in
another structured form, and (3) the only difference from the analysis --
everything else is passed through unchanged.

Checked on the richest captured live run (10390789: accepted, invalid and
dropped claims, structural support, dismissed and uncovered segments, and
every note family), replayed as in ai.tests.test_trace_equivalence.
"""

from unittest import mock

from django.test import override_settings

from ai.services.feedback import AIIssue
from ai.services.reconcile.responses import Objection
from ai.services.stages.verification import VerificationStage
from ai.tests.test_trace_equivalence import FlyerReplayCase

RUN = "10390789"
DROPPED_FAMILIES = {"ingest", "ground"}


class VerificationPayloadTests(FlyerReplayCase):

    def review(self):
        """-> (run, payload) of the run's first Verification call."""

        seen = []
        original = VerificationStage.build_input

        def capture(stage, run):
            payload = original(stage, run)
            if not seen:
                seen.append((run, payload, run.state.reconcile.analysis.ledger.payload(), list(run.state.plan_findings)))
            return payload

        with mock.patch.object(VerificationStage, "build_input", capture):
            self.replay(RUN)
        self.assertTrue(seen, "the replay never reached Verification")
        return seen[0]

    def test_what_the_ledger_leaves_out_is_never_a_routable_target(self):
        run, payload, full, _ = self.review()

        shown = {d["decision_id"] for d in payload["decision_ledger"]}
        dropped = [d for d in full if d["decision_id"] not in shown]
        self.assertTrue(dropped)
        self.assertEqual({d["decision_id"].partition(":")[0] for d in dropped}, DROPPED_FAMILIES)
        stage = VerificationStage()
        for decision in dropped:
            for kind, option in (("evidence_misread", None), ("wrong_mapping", "none")):
                objection = Objection(objection_id="V1", target_kind="decision", target_id=decision["decision_id"], kind=kind,
                                      severity="material", message="Objection.", option_id=option, excerpt="Pool A")
                outcome = stage.route(run, objection)
                self.assertIsInstance(outcome, AIIssue, decision["decision_id"])
                self.assertEqual(outcome.code, "unroutable_objection")

    def test_every_record_left_out_is_shown_in_another_form(self):
        _, payload, full, _ = self.review()

        ledger = {d["decision_id"]: d for d in payload["decision_ledger"]}
        rejected = {e["id"]: e for e in payload["rejected_claims"]}
        outcomes = set()
        for decision in full:
            family, _, subject = decision["decision_id"].partition(":")
            if decision["decision_id"] in ledger or family not in DROPPED_FAMILIES:
                continue
            outcomes.add((family, decision["outcome"]))
            if family == "ingest" and decision["outcome"] == "accepted":
                self.assertEqual(ledger[subject]["kind"], "claim")
            elif family == "ingest":
                self.assertEqual(rejected[subject]["outcome"], decision["outcome"])
            else:
                self.assertEqual(ledger[subject]["kind"], "claim")
                self.assertEqual("structural_support" in ledger[subject].get("flags", []), decision["outcome"] == "structural")
        # The run exercises every rule.
        self.assertTrue({("ingest", "accepted"), ("ground", "anchored"), ("ground", "structural")} <= outcomes, outcomes)
        self.assertTrue({o for f, o in outcomes if f == "ingest"} - {"accepted"}, outcomes)

    def test_every_other_decision_is_passed_through_unchanged(self):
        _, payload, full, _ = self.review()

        original = {d["decision_id"]: d for d in full}
        shown_segments = {s["segment_id"] for s in payload["evidence_segments"]}
        changed = 0
        for decision in payload["decision_ledger"]:
            before = original[decision["decision_id"]]
            if decision == before:
                continue
            changed += 1
            family, _, subject = decision["decision_id"].partition(":")
            if family == "cover":
                self.assertIn(subject, shown_segments)
                self.assertEqual(decision, {**before, "detail": {k: v for k, v in before["detail"].items() if k != "text"}})
            else:
                self.assertEqual(decision, {**before, "flags": [*before.get("flags", []), "structural_support"]})
        self.assertTrue(changed)
        # Order is the analysis' own.
        order = [d["decision_id"] for d in full]
        self.assertEqual([d["decision_id"] for d in payload["decision_ledger"]],
                         [key for key in order if key in {d["decision_id"] for d in payload["decision_ledger"]}])

    def test_a_segment_text_left_out_is_shown_verbatim_in_the_evidence(self):
        run, payload, full, _ = self.review()

        evidence = {s["segment_id"]: s["text"] for s in payload["evidence_segments"]}
        entries = [*payload["dismissed_segments"], *payload["uncovered_segments"]]
        self.assertTrue(entries)
        for entry in entries:
            self.assertNotIn("text", entry)
            self.assertEqual(evidence[entry["segment_id"]], run.bundle.segment(entry["segment_id"]).text)
        for decision in payload["decision_ledger"]:
            if decision["decision_id"].startswith("cover:"):
                self.assertNotIn("text", decision.get("detail", {}))
                self.assertIn(decision["decision_id"][len("cover:"):], evidence)

    @override_settings(AI_VERIFY_EVIDENCE_MAX_CHARS=400)
    def test_a_segment_not_shown_keeps_its_text(self):
        run, payload, _, _ = self.review()

        self.assertGreater(payload["segments_not_shown"], 0)
        evidence = {s["segment_id"] for s in payload["evidence_segments"]}
        hidden = 0
        for entry in [*payload["dismissed_segments"], *payload["uncovered_segments"]]:
            if entry["segment_id"] not in evidence:
                hidden += 1
                self.assertEqual(entry["text"], run.bundle.segment(entry["segment_id"]).text)
        for decision in payload["decision_ledger"]:
            segment = decision["decision_id"][len("cover:"):]
            if decision["decision_id"].startswith("cover:") and segment not in evidence:
                hidden += 1
                self.assertIn("text", decision["detail"])
        self.assertTrue(hidden)

    def test_a_note_left_out_restates_a_record_that_is_shown(self):
        run, payload, _, findings = self.review()

        rs, analysis = run.state.reconcile, run.state.reconcile.analysis
        ledger = {d["decision_id"]: d for d in payload["decision_ledger"]}
        rejected = {e["id"] for e in payload["rejected_claims"]}
        shown = {n["message"] for n in payload["notes"]}
        left_out = [f for f in findings if f.message not in shown]
        families = set()
        for finding in left_out:
            claim = rs.note_refs.get(finding.message)
            if claim is not None:
                self.assertIn(claim, rejected)
                families.add("Ignored evidence claim")
                continue
            decision = analysis.finding_refs[finding.message]
            self.assertIn(decision, ledger)
            families.add(finding.message.split(":")[0] if finding.message.startswith("Not changed") else "set aside")
        self.assertEqual(families, {"Ignored evidence claim", "Not changed", "set aside"})
        # Only the registered restatements are left out; every other note stays.
        for finding in findings:
            if finding.message not in rs.note_refs and finding.message not in analysis.finding_refs:
                self.assertIn(finding.message, shown)
