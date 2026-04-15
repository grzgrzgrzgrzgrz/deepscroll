"""
DocumentNavigator - Tools for navigating and searching large document sets.

Provides grep, chunk, and summarize operations that can be called from
LLM-generated code to efficiently navigate through large contexts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterator


@dataclass
class SearchMatch:
    """A match found in document search."""

    doc_index: int
    line_number: int
    line_content: str
    context_before: list[str]
    context_after: list[str]
    match_start: int
    match_end: int


@dataclass
class ChunkInfo:
    """Information about a text chunk."""

    index: int
    content: str
    start_char: int
    end_char: int
    start_line: int
    end_line: int


class DocumentNavigator:
    """
    Navigate and search through large document collections.

    Provides efficient operations for:
    - Searching with regex patterns
    - Chunking documents for processing
    - Summarizing document structure
    - Extracting relevant sections
    """

    def __init__(
        self,
        chunk_size: int = 4000,
        overlap: int = 200,
        context_lines: int = 3,
    ):
        """
        Initialize the navigator.

        Args:
            chunk_size: Target size for text chunks (in characters)
            overlap: Overlap between chunks to maintain context
            context_lines: Lines of context to include in search results
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.context_lines = context_lines

    def grep(
        self,
        documents: list[str],
        pattern: str,
        ignore_case: bool = False,
        max_matches: int = 100,
    ) -> list[SearchMatch]:
        """
        Search documents for a regex pattern.

        Args:
            documents: List of document contents
            pattern: Regex pattern to search for
            ignore_case: Whether to ignore case in matching
            max_matches: Maximum number of matches to return

        Returns:
            List of SearchMatch objects
        """
        flags = re.IGNORECASE if ignore_case else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}")

        matches: list[SearchMatch] = []

        for doc_idx, doc in enumerate(documents):
            lines = doc.split("\n")

            for line_num, line in enumerate(lines):
                for match in regex.finditer(line):
                    if len(matches) >= max_matches:
                        return matches

                    # Get context lines
                    context_before = lines[
                        max(0, line_num - self.context_lines) : line_num
                    ]
                    context_after = lines[
                        line_num + 1 : line_num + 1 + self.context_lines
                    ]

                    matches.append(
                        SearchMatch(
                            doc_index=doc_idx,
                            line_number=line_num + 1,  # 1-indexed
                            line_content=line,
                            context_before=context_before,
                            context_after=context_after,
                            match_start=match.start(),
                            match_end=match.end(),
                        )
                    )

        return matches

    def grep_sections(
        self,
        documents: list[str],
        pattern: str,
        section_size: int = 500,
        ignore_case: bool = False,
    ) -> list[str]:
        """
        Search and return text sections around matches.

        Args:
            documents: List of document contents
            pattern: Regex pattern to search for
            section_size: Size of text section to return around each match
            ignore_case: Whether to ignore case

        Returns:
            List of text sections containing matches
        """
        matches = self.grep(documents, pattern, ignore_case)
        sections: list[str] = []

        for match in matches:
            doc = documents[match.doc_index]
            lines = doc.split("\n")

            # Find character position of the line
            char_pos = sum(len(lines[i]) + 1 for i in range(match.line_number - 1))
            char_pos += match.match_start

            # Extract section around match
            start = max(0, char_pos - section_size // 2)
            end = min(len(doc), char_pos + section_size // 2)

            section = doc[start:end]

            # Clean up section boundaries (don't cut words)
            if start > 0:
                # Find first space
                first_space = section.find(" ")
                if first_space > 0 and first_space < 50:
                    section = "..." + section[first_space + 1 :]

            if end < len(doc):
                # Find last space
                last_space = section.rfind(" ")
                if last_space > len(section) - 50:
                    section = section[:last_space] + "..."

            sections.append(f"[Doc {match.doc_index}, Line {match.line_number}]\n{section}")

        return sections

    def chunk(self, text: str) -> list[str]:
        """
        Split text into overlapping chunks.

        Args:
            text: Text to chunk

        Returns:
            List of text chunks
        """
        if len(text) <= self.chunk_size:
            return [text]

        chunks: list[str] = []
        start = 0

        while start < len(text):
            end = start + self.chunk_size

            # Don't cut in the middle of a word
            if end < len(text):
                # Find a good break point (newline, period, or space)
                for sep in ["\n\n", "\n", ". ", " "]:
                    break_point = text.rfind(sep, start + self.chunk_size // 2, end)
                    if break_point > start:
                        end = break_point + len(sep)
                        break

            chunks.append(text[start:end])

            # Move start with overlap
            start = end - self.overlap
            if start >= len(text):
                break

        return chunks

    def chunk_with_info(self, text: str) -> list[ChunkInfo]:
        """
        Split text into chunks with position information.

        Args:
            text: Text to chunk

        Returns:
            List of ChunkInfo objects with position data
        """
        chunks = self.chunk(text)
        result: list[ChunkInfo] = []

        char_pos = 0
        lines = text.split("\n")
        line_starts = [0]
        for line in lines[:-1]:
            line_starts.append(line_starts[-1] + len(line) + 1)

        for i, chunk_text in enumerate(chunks):
            # Find start/end lines
            start_line = self._find_line_at_pos(line_starts, char_pos)
            end_char = char_pos + len(chunk_text)
            end_line = self._find_line_at_pos(line_starts, end_char - 1)

            result.append(
                ChunkInfo(
                    index=i,
                    content=chunk_text,
                    start_char=char_pos,
                    end_char=end_char,
                    start_line=start_line,
                    end_line=end_line,
                )
            )

            # Next chunk starts with overlap
            char_pos = end_char - self.overlap

        return result

    def _find_line_at_pos(self, line_starts: list[int], pos: int) -> int:
        """Find line number at character position."""
        for i, start in enumerate(line_starts):
            if start > pos:
                return i  # 1-indexed
        return len(line_starts)

    def summarize(
        self,
        text: str,
        head_lines: int = 20,
        tail_lines: int = 20,
    ) -> str:
        """
        Get a summary view of a document (head + tail).

        Args:
            text: Document text
            head_lines: Number of lines from start
            tail_lines: Number of lines from end

        Returns:
            Summary with head, stats, and tail
        """
        lines = text.split("\n")
        total_lines = len(lines)
        total_chars = len(text)

        if total_lines <= head_lines + tail_lines:
            return text

        head = "\n".join(lines[:head_lines])
        tail = "\n".join(lines[-tail_lines:])

        return f"""{head}

... [{total_lines - head_lines - tail_lines} lines omitted, {total_chars:,} total chars] ...

{tail}"""

    def extract_sections(
        self,
        text: str,
        section_pattern: str = r"^#{1,3}\s+.+$",
    ) -> list[tuple[str, str]]:
        """
        Extract sections based on header patterns.

        Args:
            text: Document text
            section_pattern: Regex pattern for section headers

        Returns:
            List of (header, content) tuples
        """
        regex = re.compile(section_pattern, re.MULTILINE)
        matches = list(regex.finditer(text))

        if not matches:
            return [("", text)]

        sections: list[tuple[str, str]] = []

        for i, match in enumerate(matches):
            header = match.group()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
            content = text[start:end].strip()
            sections.append((header, content))

        return sections

    def find_code_blocks(self, text: str) -> list[tuple[str, str]]:
        """
        Find fenced code blocks in markdown.

        Args:
            text: Markdown text

        Returns:
            List of (language, code) tuples
        """
        pattern = r"```(\w*)\n(.*?)```"
        matches = re.findall(pattern, text, re.DOTALL)
        return [(lang or "text", code.strip()) for lang, code in matches]

    def iter_lines(self, text: str) -> Iterator[tuple[int, str]]:
        """
        Iterate over lines with line numbers.

        Args:
            text: Text to iterate

        Yields:
            (line_number, line_content) tuples
        """
        for i, line in enumerate(text.split("\n"), 1):
            yield i, line

    def get_line_range(
        self,
        text: str,
        start: int,
        end: int,
    ) -> str:
        """
        Get a range of lines from text.

        Args:
            text: Source text
            start: Start line (1-indexed)
            end: End line (inclusive)

        Returns:
            Lines in the specified range
        """
        lines = text.split("\n")
        start_idx = max(0, start - 1)
        end_idx = min(len(lines), end)
        return "\n".join(lines[start_idx:end_idx])

    def word_count(self, text: str) -> dict[str, int]:
        """
        Count words in text.

        Args:
            text: Text to analyze

        Returns:
            Dictionary with word statistics
        """
        words = re.findall(r"\b\w+\b", text.lower())
        return {
            "total_words": len(words),
            "unique_words": len(set(words)),
            "total_chars": len(text),
            "total_lines": text.count("\n") + 1,
        }

    def find_similar_lines(
        self,
        documents: list[str],
        query_line: str,
        threshold: float = 0.6,
        max_results: int = 20,
    ) -> list[tuple[int, int, str, float]]:
        """
        Find lines similar to a query using simple word overlap.

        Args:
            documents: List of document contents
            query_line: Line to match against
            threshold: Minimum similarity score (0-1)
            max_results: Maximum results to return

        Returns:
            List of (doc_index, line_number, line, score) tuples
        """
        query_words = set(re.findall(r"\b\w+\b", query_line.lower()))
        if not query_words:
            return []

        results: list[tuple[int, int, str, float]] = []

        for doc_idx, doc in enumerate(documents):
            for line_num, line in enumerate(doc.split("\n"), 1):
                line_words = set(re.findall(r"\b\w+\b", line.lower()))
                if not line_words:
                    continue

                # Jaccard similarity
                intersection = len(query_words & line_words)
                union = len(query_words | line_words)
                score = intersection / union if union > 0 else 0

                if score >= threshold:
                    results.append((doc_idx, line_num, line, score))

        # Sort by score descending
        results.sort(key=lambda x: x[3], reverse=True)
        return results[:max_results]
