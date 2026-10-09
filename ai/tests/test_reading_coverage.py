"""
Phase 3 of .Documentation/reconcile-architecture-plan.md: coverage of
structure in Reading terms (read / ignored / unread), never per-segment
dismissal of table content.
"""

from ai.services.reconcile import readings as rd
from ai.tests.test_readings import ReadingFixture


class StructuredCoverageTests(ReadingFixture):

    def test_every_column_and_heading_is_read_ignored_or_unread(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())
        coverage = analysis.structured_coverage

        self.assertEqual(coverage["S1#t3.c2"]["status"], rd.READ_)
        self.assertEqual(coverage["S1#t2.c3"]["status"], rd.IGNORED)  # 'Primary use': a Reading's `none`
        self.assertEqual(coverage["S1#1"]["status"], rd.READ_)  # the title names the tournament
        self.assertEqual(coverage["S1#5"]["status"], rd.IGNORED)  # 'Teams' names a kind, not an entity
        ignored = analysis.ledger.get("cover:S1#t2.c3")
        self.assertEqual((ignored.kind, ignored.outcome), ("coverage", "ignored"))
        self.assertEqual(ignored.inputs, ("read:rd/S1#t2/role/c3",))  # a semantic decision, resting on its slot

    def test_a_table_without_a_validated_reading_is_unread_and_reported(self):
        readings = [r for r in self.readings() if r.element_id != "S1#t3"]
        analysis = self.analyse_readings(readings, items=self.prose_claims())

        self.assertEqual({analysis.structured_coverage[f"S1#t3.c{k}"]["status"] for k in (1, 2, 3)}, {rd.UNREAD})
        self.assertEqual(analysis.ledger.get("cover:S1#t3.c2").outcome, rd.UNREAD)
        self.assertTrue(any("S1#t3.c2" in f.message for f in analysis.findings))

    def test_structured_segments_are_never_segment_coverage_entries(self):
        analysis = self.analyse_readings(self.readings(), items=self.prose_claims())

        structured = {s.segment_id for s in self.bundle_.segments() if s.kind in ("table", "table_row")}
        self.assertFalse(set(analysis.coverage) & structured)
        # The lexical false positive of the claims-mode runs ('Final' inside a
        # venue row's 'Opening match and final') cannot arise: the venue table
        # is never a per-segment coverage subject.
        self.assertNotIn("S1#t2.r1", analysis.coverage)

    def test_a_dismissal_of_table_content_is_never_recorded(self):
        import types

        from ai.services.reconcile.responses import SegmentDismissal
        from ai.services.reconcile.state import ReconcileState
        from ai.services.stages.extraction import record_dismissals

        readings = self.readings()
        rs = ReconcileState(evidence_mode="readings", readings=readings, prose_scope=rd.prose_eligible(self.document, readings))
        run = types.SimpleNamespace(state=types.SimpleNamespace(reconcile=rs), bundle=self.bundle_)
        record_dismissals(run, [SegmentDismissal(segment_id="S1#t3.r1", reason="Lists a fixture, not a venue."),
                                SegmentDismissal(segment_id="S1#12", reason="Scoring rules.")])

        self.assertEqual(set(rs.dismissals), {"S1#12"})
