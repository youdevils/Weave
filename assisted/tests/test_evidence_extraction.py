from django.test import SimpleTestCase

from assisted.services.evidence_extraction import (
    EvidenceExtractionError,
    UnsupportedEvidenceType,
    bounded,
    extract_text,
)
from assisted.tests.support import build_minimal_docx, build_minimal_pdf


class ExtractTextTests(SimpleTestCase):

    def test_plain_text_is_returned_as_is(self):
        result = extract_text(b"hello evidence", filename="notes.txt")

        self.assertEqual(result.text, "hello evidence")
        self.assertTrue(result.mime_type.startswith("text/"))

    def test_invalid_utf8_text_is_rejected(self):
        with self.assertRaises(EvidenceExtractionError):
            extract_text(b"\xff\xfe\x00\x01", filename="bad.txt")

    def test_pdf_text_is_extracted(self):
        pdf_bytes = build_minimal_pdf("Hello from a quarterly report")

        result = extract_text(pdf_bytes, filename="report.pdf")

        self.assertIn("Hello from a quarterly report", result.text)
        self.assertEqual(result.mime_type, "application/pdf")

    def test_corrupt_pdf_is_rejected(self):
        with self.assertRaises(EvidenceExtractionError):
            extract_text(b"%PDF-1.4\nnot a real pdf", filename="broken.pdf")

    def test_docx_text_is_extracted(self):
        docx_bytes = build_minimal_docx("Hello from a Word document")

        result = extract_text(docx_bytes, filename="notes.docx")

        self.assertIn("Hello from a Word document", result.text)

    def test_unsupported_type_is_rejected(self):
        png_header = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32

        with self.assertRaises(UnsupportedEvidenceType):
            extract_text(png_header, filename="image.png")

    def test_zip_that_is_not_named_docx_is_rejected(self):
        # A zip (or zip-like) file that isn't a .docx-named upload must not
        # be treated as one just because the mime sniff is ambiguous.
        zip_header = b"PK\x03\x04" + b"\x00" * 32

        with self.assertRaises(UnsupportedEvidenceType):
            extract_text(zip_header, filename="archive.zip")


class BoundedTests(SimpleTestCase):

    def test_short_text_is_untouched(self):
        self.assertEqual(bounded("short", max_chars=100), "short")

    def test_long_text_is_truncated_with_an_indicator(self):
        text = "x" * 200

        result = bounded(text, max_chars=50)

        self.assertTrue(result.startswith("x" * 50))
        self.assertIn("truncated", result)
        self.assertLess(len(result), len(text))
