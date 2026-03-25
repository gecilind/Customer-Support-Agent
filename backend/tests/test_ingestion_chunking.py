"""Unit tests for section header detection and chunking (regex + integration)."""

import unittest

from services.ingestion_service import (
    IngestionService,
    _RE_CHAPTER_HEADER,
    _RE_MARKDOWN_HEADER,
    _RE_NUMBERED_HEADER,
)


class TestSectionHeaderRegex(unittest.TestCase):
    def test_numbered_simple(self) -> None:
        self.assertIsNotNone(_RE_NUMBERED_HEADER.match("1. Getting Started"))
        self.assertIsNotNone(_RE_NUMBERED_HEADER.match("9. Warranty Information"))

    def test_numbered_nested(self) -> None:
        self.assertIsNotNone(_RE_NUMBERED_HEADER.match("2.1 OPC UA"))
        self.assertIsNotNone(
            _RE_NUMBERED_HEADER.match("2.1.1.1 How to use the OPC UA Client")
        )

    def test_decimal_numbered(self) -> None:
        self.assertIsNotNone(_RE_NUMBERED_HEADER.match("1.0 Introduction"))
        self.assertIsNotNone(_RE_NUMBERED_HEADER.match("3.2.1 Configuration"))

    def test_chapter(self) -> None:
        self.assertIsNotNone(_RE_CHAPTER_HEADER.match("Chapter 1: Overview"))
        self.assertIsNotNone(_RE_CHAPTER_HEADER.match("Chapter 12: Troubleshooting"))

    def test_markdown(self) -> None:
        self.assertIsNotNone(_RE_MARKDOWN_HEADER.match("# Heading"))
        self.assertIsNotNone(_RE_MARKDOWN_HEADER.match("## Sub Heading"))
        self.assertIsNotNone(_RE_MARKDOWN_HEADER.match("### Sub Sub Heading"))


class TestIngestionChunkingIntegration(unittest.TestCase):
    def _svc(self) -> IngestionService:
        return IngestionService.__new__(IngestionService)  # noqa: PLC3002

    def test_chunk_text_splits_numbered_sections(self) -> None:
        svc = self._svc()
        # Bodies must be >= 50 chars so _merge_short_sections does not merge them.
        long_a = "A" * 52
        long_b = "B" * 52
        doc = (
            "1. Getting Started\n\n"
            f"{long_a}\n\n"
            "2.1.1.1 How to use the OPC UA Client\n\n"
            f"{long_b}\n"
        )
        chunks, labels = svc._chunk_text(doc, max_chars=2000)
        self.assertGreaterEqual(len(labels), 2)
        self.assertTrue(any("1. Getting Started" in c for _, c in chunks))
        self.assertTrue(any("2.1.1.1 How to use the OPC UA Client" in c for _, c in chunks))

    def test_no_headers_fallback_part_labels(self) -> None:
        svc = self._svc()
        doc = "Alpha paragraph.\n\nBeta paragraph.\n\nGamma here."
        chunks, labels = svc._chunk_text(doc, max_chars=2000)
        self.assertGreaterEqual(len(chunks), 1)
        self.assertTrue(all(l.startswith("Part ") for l in labels))

    def test_all_caps_header_after_blank(self) -> None:
        svc = self._svc()
        doc = "Intro line.\n\nGETTING STARTED\n\nBody text here."
        chunks, labels = svc._chunk_text(doc, max_chars=2000)
        self.assertIn("GETTING STARTED", labels)
        self.assertTrue(any("GETTING STARTED" in c for _, c in chunks))


if __name__ == "__main__":
    unittest.main()
