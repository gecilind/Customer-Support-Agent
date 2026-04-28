from __future__ import annotations

import re

from core.exceptions import IngestionError
from repositories.manual_repository import ManualRepository
from services.embedding_service import EmbeddingService
from services.zendesk_service import ZendeskArticle, ZendeskService

# Numbered / decimal section titles: "1. Getting Started", "2.1 OPC UA", "2.1.1.1 How to use..."
_RE_NUMBERED_HEADER = re.compile(r"^\d+(\.\d+)*\.?\s+\S")
# Nested outline numbers (2.1, 4.3.14, …) are always section headers — never procedure steps.
_RE_NESTED_NUMBERED_START = re.compile(r"^\d+\.\d+")
# Single top-level number + space ("5. Lift the…") — may be a real title or a numbered step.
_RE_SIMPLE_NUMBERED_START = re.compile(r"^(\d+)\.\s+")
_RE_CHAPTER_HEADER = re.compile(r"^Chapter\s+\d+", re.IGNORECASE)
_RE_MARKDOWN_HEADER = re.compile(r"^#{1,6}\s+")


class IngestionService:
    def __init__(self, manual_repository: ManualRepository, embedding_service: EmbeddingService) -> None:
        self.manual_repository = manual_repository
        self.embedding_service = embedding_service

    async def ingest_text(
        self,
        *,
        source: str,
        raw_text: str,
        category: str = "general",
        file_type: str = "txt",
    ) -> int:
        section_chunks, ordered_section_labels = self._chunk_text(raw_text)
        chunk_texts = [text for _, text in section_chunks]
        embeddings = await self.embedding_service.generate(chunk_texts)
        sections_and_chunks = [
            (section_label, index, chunk_text, embeddings[index])
            for index, (section_label, chunk_text) in enumerate(section_chunks)
        ]

        labels_preview = ordered_section_labels[:10]
        labels_str = ", ".join(repr(l) for l in labels_preview)
        if len(ordered_section_labels) > 10:
            labels_str += ", ..."

        print(f"[INGEST] File: {source}")
        print(f"[INGEST] Type: {file_type}")
        print(f"[INGEST] Total sections detected: {len(ordered_section_labels)}")
        print(f"[INGEST] Total chunks created: {len(section_chunks)}")
        print(f"[INGEST] Sections: [{labels_str}]")

        return await self.manual_repository.save_chunks(
            source=source,
            category=category,
            sections_and_chunks=sections_and_chunks,
        )

    def _chunk_text(
        self, text: str, max_chars: int = 2000
    ) -> tuple[list[tuple[str, str]], list[str]]:
        """Return (section_label, chunk_text) per chunk and ordered unique section labels."""
        normalized = self._normalize_document_text(text)
        if not normalized:
            return [], []

        lines = normalized.splitlines()
        header_indices = self._find_header_line_indices(lines)
        if not header_indices:
            chunks = self._chunk_fallback_paragraphs(normalized, max_chars)
            ordered = self._ordered_unique_labels(chunks)
            return chunks, ordered

        sections = self._build_sections_from_headers(lines, header_indices)
        sections = self._merge_short_sections(sections, min_body_chars=50)
        section_chunks: list[tuple[str, str]] = []
        for label, body in sections:
            section_chunks.extend(self._chunks_for_section(label, body, max_chars))
        out = [(label, chunk) for label, chunk in section_chunks if chunk.strip()]
        ordered = self._ordered_unique_labels(out)
        return out, ordered

    @staticmethod
    def _ordered_unique_labels(chunks: list[tuple[str, str]]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for label, _ in chunks:
            if label not in seen:
                seen.add(label)
                ordered.append(label)
        return ordered

    @staticmethod
    def _normalize_document_text(text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _find_header_line_indices(self, lines: list[str]) -> list[int]:
        indices: list[int] = []
        prev_line_blank = True
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                prev_line_blank = True
                continue
            if self._is_section_header_line(stripped, prev_line_blank, i, lines):
                indices.append(i)
            prev_line_blank = False
        return indices

    def _is_section_header_line(
        self, stripped: str, prev_line_blank: bool, line_idx: int, lines: list[str]
    ) -> bool:
        if _RE_MARKDOWN_HEADER.match(stripped):
            return True
        if _RE_CHAPTER_HEADER.match(stripped):
            return True
        if _RE_NUMBERED_HEADER.match(stripped):
            if _RE_NESTED_NUMBERED_START.match(stripped):
                return True
            if _RE_SIMPLE_NUMBERED_START.match(stripped):
                return self._is_simple_numbered_section_header(
                    stripped, prev_line_blank, line_idx, lines
                )
            return True
        if prev_line_blank or line_idx == 0:
            if 3 <= len(stripped) <= 100 and self._is_all_caps_header_line(stripped):
                return True
        return False

    def _neighbor_non_empty_stripped(self, lines: list[str], line_idx: int) -> tuple[str | None, str | None]:
        prev_text: str | None = None
        for j in range(line_idx - 1, -1, -1):
            s = lines[j].strip()
            if s:
                prev_text = s
                break
        next_text: str | None = None
        for j in range(line_idx + 1, len(lines)):
            s = lines[j].strip()
            if s:
                next_text = s
                break
        return prev_text, next_text

    def _is_simple_numbered_section_header(
        self, stripped: str, prev_line_blank: bool, line_idx: int, lines: list[str]
    ) -> bool:
        """True if a simple 'N. Title' line is a document section header, not a procedure step."""
        m = _RE_SIMPLE_NUMBERED_START.match(stripped)
        if not m:
            return False
        current_num = int(m.group(1))

        if line_idx > 0 and not prev_line_blank:
            return False

        prev_text, next_text = self._neighbor_non_empty_stripped(lines, line_idx)

        if prev_text is not None:
            pm = _RE_SIMPLE_NUMBERED_START.match(prev_text)
            if pm and int(pm.group(1)) == current_num - 1:
                return False

        if next_text is not None:
            nm = _RE_SIMPLE_NUMBERED_START.match(next_text)
            if nm and int(nm.group(1)) == current_num + 1:
                return False

        return True

    @staticmethod
    def _is_all_caps_header_line(s: str) -> bool:
        """True for title-like ALL CAPS lines; reject long runs of caps with no spaces (body text)."""
        if not any(c.isalpha() for c in s):
            return False
        for c in s:
            if c.isalpha() and not c.isupper():
                return False
        if " " not in s and len(s) > 40:
            return False
        return True

    def _build_sections_from_headers(
        self, lines: list[str], header_indices: list[int]
    ) -> list[tuple[str, str]]:
        sections: list[tuple[str, str]] = []
        first = header_indices[0]
        if first > 0:
            intro_lines = lines[:first]
            intro_block = "\n".join(intro_lines).strip()
            if intro_block:
                intro_label = self._intro_label_from_block(intro_lines)
                sections.append((intro_label, intro_block))

        for hi, hidx in enumerate(header_indices):
            header_line = lines[hidx].strip()
            next_start = header_indices[hi + 1] if hi + 1 < len(header_indices) else len(lines)
            body_lines = lines[hidx + 1 : next_start]
            body = "\n".join(body_lines).strip()
            sections.append((header_line, body))
        return sections

    def _intro_label_from_block(self, intro_lines: list[str]) -> str:
        for line in intro_lines:
            s = line.strip()
            if s:
                return s if len(s) >= 3 else "Introduction"
        return "Introduction"

    def _merge_short_sections(
        self, sections: list[tuple[str, str]], min_body_chars: int = 50
    ) -> list[tuple[str, str]]:
        """Merge sections with short or empty body into the following section."""
        if not sections:
            return []
        buf = list(sections)
        i = 0
        while i < len(buf):
            _, body = buf[i]
            b = body.strip()
            if len(b) < min_body_chars and i + 1 < len(buf):
                next_label, next_body = buf[i + 1]
                merged = (b + "\n\n" + next_body.strip()).strip() if b else next_body.strip()
                buf[i + 1] = (next_label, merged)
                del buf[i]
                continue
            i += 1
        if len(buf) >= 2 and len(buf[-1][1].strip()) < min_body_chars:
            pl, pb = buf[-2]
            ll, lb = buf[-1]
            buf[-2] = (pl, (pb.strip() + "\n\n" + lb.strip()).strip())
            buf.pop()
        return buf

    def _chunks_for_section(self, section_label: str, body: str, max_chars: int) -> list[tuple[str, str]]:
        """First chunk includes header + body start; later chunks are continuations only."""
        body = body.strip()
        if not body:
            return []
        full = f"{section_label}\n\n{body}"
        if len(full) <= max_chars:
            return [(section_label, full)]

        header_prefix = f"{section_label}\n\n"
        budget_first = max_chars - len(header_prefix)
        if budget_first <= 0:
            return self._split_fixed_width(full, section_label, max_chars)

        first_body_taken = self._take_prefix_prefer_paragraphs(body, budget_first)
        if not first_body_taken:
            first_body_taken = body[:budget_first]
        chunks: list[tuple[str, str]] = [(section_label, header_prefix + first_body_taken)]
        remaining = body[len(first_body_taken) :]
        while True:
            remaining = remaining.lstrip()
            if not remaining:
                break
            taken = self._take_prefix_prefer_paragraphs(remaining, max_chars)
            if not taken:
                taken = remaining[:max_chars]
            chunks.append((section_label, taken.strip()))
            remaining = remaining[len(taken) :]
        return [(lab, ch) for lab, ch in chunks if ch.strip()]

    def _take_prefix_prefer_paragraphs(self, text: str, limit: int) -> str:
        """Take a prefix up to limit chars; prefer ending at a paragraph break (double newline)."""
        if len(text) <= limit:
            return text
        window = text[:limit]
        last_break = window.rfind("\n\n")
        if last_break >= 1:
            return window[:last_break]
        last_nl = window.rfind("\n")
        if last_nl >= 1:
            return window[:last_nl]
        return window

    def _split_fixed_width(self, full: str, section_label: str, max_chars: int) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        start = 0
        while start < len(full):
            part = full[start : start + max_chars].strip()
            if part:
                out.append((section_label, part))
            start += max_chars
        return out

    def _chunk_fallback_paragraphs(self, normalized: str, max_chars: int) -> list[tuple[str, str]]:
        """No section headers: split on blank lines; labels Part 1, Part 2, …"""
        split_by_paragraph = [part.strip() for part in normalized.split("\n\n") if part.strip()]
        chunks: list[str] = []
        for para in split_by_paragraph:
            if len(para) <= max_chars:
                chunks.append(para)
                continue
            start = 0
            while start < len(para):
                piece = para[start : start + max_chars].strip()
                if piece:
                    chunks.append(piece)
                start += max_chars
        return [(f"Part {idx + 1}", c) for idx, c in enumerate(chunks) if c]

    async def ingest_zendesk(self, zendesk_service: ZendeskService) -> int:
        """
        Pulls all articles from Zendesk, chunks each title+body,
        embeds, and saves via the existing manual_repository.
        Returns total chunks saved.
        """
        articles: list[ZendeskArticle] = await zendesk_service.fetch_all_articles()

        prefix = zendesk_service.source_url_prefix_for_deletion()
        deleted = await self.manual_repository.delete_by_source_prefix(prefix=prefix)
        if deleted:
            print(f"[INGEST] Removed {deleted} existing chunk(s) under Zendesk source prefix")

        categories_sorted = sorted({a.category_name for a in articles})
        print(f"[INGEST] Source: zendesk")
        print(f"[INGEST] Locale: {zendesk_service.locale}")
        print(f"[INGEST] Articles fetched: {len(articles)}")
        print(f"[INGEST] Categories: {categories_sorted}")

        article_chunk_rows: list[tuple[ZendeskArticle, list[tuple[str, int, str]]]] = []
        all_texts: list[str] = []

        for article in sorted(articles, key=lambda a: (a.category_name, a.title, a.article_id)):
            full = f"{article.title}\n\n{article.body_text}"
            normalized = self._normalize_document_text(full)
            if not normalized:
                continue
            rows: list[tuple[str, int, str]] = []
            if len(normalized) <= 2000:
                rows.append((article.section_name, 0, normalized))
            else:
                for idx, (_part_label, chunk_text) in enumerate(
                    self._chunk_fallback_paragraphs(normalized, 2000)
                ):
                    if chunk_text.strip():
                        rows.append((article.section_name, idx, chunk_text))
            if not rows:
                continue
            article_chunk_rows.append((article, rows))
            all_texts.extend(text for _, _, text in rows)

        if not all_texts:
            print("[INGEST] Total chunks created: 0")
            return 0

        all_embeddings: list[list[float]] = []
        batch_size = 100
        for start in range(0, len(all_texts), batch_size):
            batch = all_texts[start : start + batch_size]
            all_embeddings.extend(await self.embedding_service.generate(batch))

        if len(all_embeddings) != len(all_texts):
            raise IngestionError(
                f"Embedding batch mismatch: texts={len(all_texts)}, embeddings={len(all_embeddings)}"
            )

        total_saved = 0
        offset = 0
        for article, rows in article_chunk_rows:
            n = len(rows)
            slice_emb = all_embeddings[offset : offset + n]
            offset += n
            sections_and_chunks = [
                (rows[i][0], rows[i][1], rows[i][2], slice_emb[i]) for i in range(n)
            ]
            total_saved += await self.manual_repository.save_chunks(
                source=article.html_url,
                category=article.category_name,
                sections_and_chunks=sections_and_chunks,
            )

        print(f"[INGEST] Total chunks created: {total_saved}")
        return total_saved
