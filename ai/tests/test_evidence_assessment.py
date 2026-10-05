"""
Unit coverage for ai.services.evidence_assessment.assess_change_plan -- the
deterministic OJ-side backstop over a Change Plan's self-reported
EvidenceAssessment verdicts. These tests call the function directly, with
hand-built ChangePlan/ChangeAction fixtures, rather than driving the full
orchestrator loop (see ai.tests.test_orchestrator_reconcile for the
integration-level proof that this function is actually wired in).
"""

from django.test import SimpleTestCase

from ai.services.change_plan import ChangeAction, ChangePlan, EntityRef, EvidenceAssessment, EvidenceItem
from ai.services.evidence_assessment import assess_change_plan


def _action(operation="create", verdict="supported", evidence=(), target_id="obj-1"):
    kind = "new" if operation == "create" else "existing"
    return ChangeAction(
        operation=operation,
        target_type="Object",
        target_ref=EntityRef(kind=kind, id=target_id),
        parent_ref=EntityRef(kind="existing", id="type-1") if operation == "create" else None,
        fields={"name": "Something"} if operation == "create" else [],
        assessment=EvidenceAssessment(verdict=verdict, reasoning="Because."),
        evidence=list(evidence),
    )


def _plan(*actions):
    return ChangePlan(summary="", actions=list(actions))


class AssessChangePlanTests(SimpleTestCase):

    def test_supported_create_with_no_evidence_passes(self):
        issues = assess_change_plan(_plan(_action("create", "supported", evidence=())))
        self.assertEqual(issues, [])

    def test_supported_update_with_no_evidence_passes(self):
        issues = assess_change_plan(_plan(_action("update", "supported", evidence=())))
        self.assertEqual(issues, [])

    def test_supported_delete_with_evidence_passes(self):
        issues = assess_change_plan(
            _plan(_action("delete", "supported", evidence=[EvidenceItem(source="doc.txt")]))
        )
        self.assertEqual(issues, [])

    def test_supported_delete_without_evidence_is_downgraded(self):
        issues = assess_change_plan(_plan(_action("delete", "supported", evidence=())))

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "delete_requires_evidence")

    def test_each_non_supported_verdict_produces_an_issue(self):
        for verdict in ("unsupported", "ambiguous", "conflicting", "requires_more_context"):
            with self.subTest(verdict=verdict):
                issues = assess_change_plan(_plan(_action("create", verdict)))
                self.assertEqual(len(issues), 1)
                self.assertEqual(issues[0].code, "candidate_not_supported")
                self.assertIn(verdict, issues[0].message)

    def test_unsupported_delete_produces_only_the_candidate_issue_not_both(self):
        """A delete that's already unsupported shouldn't also get flagged
        for missing evidence -- one issue per defective action, not a pile-on."""
        issues = assess_change_plan(_plan(_action("delete", "unsupported", evidence=())))

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].code, "candidate_not_supported")

    def test_mixed_plan_reports_an_issue_per_defective_action_only(self):
        good = _action("create", "supported", target_id="tmp:good")
        bad = _action("create", "unsupported", target_id="tmp:bad")

        issues = assess_change_plan(_plan(good, bad))

        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].target_ref.id, "tmp:bad")

    def test_empty_plan_produces_no_issues(self):
        self.assertEqual(assess_change_plan(_plan()), [])
