from django.test import SimpleTestCase

from model.services.proposal.review import ProposalReviewService


class CardinalityFormattingTests(SimpleTestCase):
    """
    Regression coverage for the cardinality-renders-as-float bug: once
    ai.services.change_plan.FieldValue stops forcing clean integers into
    floats, _cardinality's bare f-string must render "1..1", not "1.0..1.0",
    for every representative integer value.
    """

    def test_representative_integers_render_without_decimal(self):
        for value in (0, 1, 2, 8, 10):
            with self.subTest(value=value):
                self.assertEqual(
                    ProposalReviewService._cardinality(value, value),
                    f"{value}..{value}",
                )

    def test_unbounded_maximum_renders_as_asterisk(self):
        self.assertEqual(ProposalReviewService._cardinality(0, None), "0..*")

    def test_rejects_float_regression(self):
        # Guards against the original bug reappearing upstream: a float
        # reaching this method would render as "1.0..1.0".
        self.assertNotEqual(ProposalReviewService._cardinality(1, 1), "1.0..1.0")
