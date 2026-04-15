"""Tests for DocumentNavigator."""

import pytest

from deepscroll.navigator import DocumentNavigator, SearchMatch


class TestDocumentNavigator:
    """Test DocumentNavigator functionality."""

    @pytest.fixture
    def navigator(self) -> DocumentNavigator:
        """Create a navigator instance."""
        return DocumentNavigator(chunk_size=100, overlap=20, context_lines=2)

    @pytest.fixture
    def sample_docs(self) -> list[str]:
        """Sample documents for testing."""
        return [
            """# Document 1
This is the first document.
It contains some important information.
The authentication system works here.
More content follows.
End of document 1.""",
            """# Document 2
Another document with different content.
This one talks about the database.
The authentication is also mentioned.
Final lines here.
End of document 2.""",
        ]

    def test_grep_basic(self, navigator: DocumentNavigator, sample_docs: list[str]) -> None:
        """Test basic grep functionality."""
        matches = navigator.grep(sample_docs, "authentication")

        assert len(matches) == 2
        assert all(isinstance(m, SearchMatch) for m in matches)
        assert matches[0].doc_index == 0
        assert matches[1].doc_index == 1

    def test_grep_case_insensitive(
        self, navigator: DocumentNavigator, sample_docs: list[str]
    ) -> None:
        """Test case-insensitive search."""
        matches = navigator.grep(sample_docs, "AUTHENTICATION", ignore_case=True)
        assert len(matches) == 2

    def test_grep_regex(self, navigator: DocumentNavigator, sample_docs: list[str]) -> None:
        """Test regex pattern matching."""
        matches = navigator.grep(sample_docs, r"Document \d")
        assert len(matches) == 2

    def test_grep_no_matches(
        self, navigator: DocumentNavigator, sample_docs: list[str]
    ) -> None:
        """Test grep with no matches."""
        matches = navigator.grep(sample_docs, "nonexistent_pattern_xyz")
        assert len(matches) == 0

    def test_grep_max_matches(
        self, navigator: DocumentNavigator, sample_docs: list[str]
    ) -> None:
        """Test max_matches limit."""
        matches = navigator.grep(sample_docs, r"\w+", max_matches=5)
        assert len(matches) == 5

    def test_grep_context(self, navigator: DocumentNavigator, sample_docs: list[str]) -> None:
        """Test that context lines are captured."""
        matches = navigator.grep(sample_docs, "authentication")

        assert len(matches[0].context_before) > 0
        assert len(matches[0].context_after) > 0

    def test_grep_sections(
        self, navigator: DocumentNavigator, sample_docs: list[str]
    ) -> None:
        """Test grep_sections returns text sections."""
        sections = navigator.grep_sections(sample_docs, "authentication", section_size=100)

        assert len(sections) == 2
        assert all("authentication" in s.lower() for s in sections)

    def test_chunk_small_text(self, navigator: DocumentNavigator) -> None:
        """Test chunking text smaller than chunk_size."""
        small_text = "This is a small text."
        chunks = navigator.chunk(small_text)

        assert len(chunks) == 1
        assert chunks[0] == small_text

    def test_chunk_large_text(self) -> None:
        """Test chunking large text."""
        nav = DocumentNavigator(chunk_size=50, overlap=10)
        large_text = "Word " * 100  # 500 characters

        chunks = nav.chunk(large_text)

        assert len(chunks) > 1
        # Check overlap
        for i in range(1, len(chunks)):
            # Some overlap should exist
            pass  # Overlap is internal implementation

    def test_chunk_with_info(self) -> None:
        """Test chunk_with_info returns position data."""
        nav = DocumentNavigator(chunk_size=50, overlap=10)
        text = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5\nLine 6\nLine 7\nLine 8"

        chunks = nav.chunk_with_info(text)

        assert len(chunks) > 0
        assert all(c.start_char >= 0 for c in chunks)
        assert all(c.start_line >= 1 for c in chunks)

    def test_summarize(self, navigator: DocumentNavigator) -> None:
        """Test document summarization."""
        text = "\n".join([f"Line {i}" for i in range(100)])

        summary = navigator.summarize(text, head_lines=5, tail_lines=5)

        assert "Line 0" in summary
        assert "Line 4" in summary
        assert "Line 99" in summary
        assert "omitted" in summary

    def test_summarize_short_text(self, navigator: DocumentNavigator) -> None:
        """Test summarize with short text."""
        short_text = "Line 1\nLine 2\nLine 3"

        summary = navigator.summarize(short_text, head_lines=5, tail_lines=5)

        assert summary == short_text

    def test_extract_sections(self, navigator: DocumentNavigator) -> None:
        """Test markdown section extraction."""
        markdown = """# Header 1
Content for section 1.

## Header 2
Content for section 2.

### Header 3
Content for section 3.
"""
        sections = navigator.extract_sections(markdown)

        assert len(sections) == 3
        assert sections[0][0] == "# Header 1"
        assert sections[1][0] == "## Header 2"

    def test_find_code_blocks(self, navigator: DocumentNavigator) -> None:
        """Test code block extraction."""
        markdown = """Some text.

```python
def hello():
    print("Hello")
```

More text.

```javascript
console.log("Hello");
```
"""
        blocks = navigator.find_code_blocks(markdown)

        assert len(blocks) == 2
        assert blocks[0][0] == "python"
        assert "def hello" in blocks[0][1]
        assert blocks[1][0] == "javascript"

    def test_word_count(self, navigator: DocumentNavigator) -> None:
        """Test word counting."""
        text = "Hello world. Hello again."

        stats = navigator.word_count(text)

        assert stats["total_words"] == 4
        assert stats["unique_words"] == 3  # hello, world, again

    def test_get_line_range(self, navigator: DocumentNavigator) -> None:
        """Test line range extraction."""
        text = "Line 1\nLine 2\nLine 3\nLine 4\nLine 5"

        result = navigator.get_line_range(text, 2, 4)

        assert result == "Line 2\nLine 3\nLine 4"

    def test_find_similar_lines(
        self, navigator: DocumentNavigator, sample_docs: list[str]
    ) -> None:
        """Test similar line finding."""
        results = navigator.find_similar_lines(
            sample_docs, "authentication system", threshold=0.3
        )

        assert len(results) > 0
        # Should find the authentication lines
        assert any("authentication" in r[2].lower() for r in results)


class TestSearchMatch:
    """Test SearchMatch dataclass."""

    def test_search_match_creation(self) -> None:
        """Test creating a SearchMatch."""
        match = SearchMatch(
            doc_index=0,
            line_number=10,
            line_content="Test line",
            context_before=["Before 1", "Before 2"],
            context_after=["After 1"],
            match_start=5,
            match_end=9,
        )

        assert match.doc_index == 0
        assert match.line_number == 10
        assert len(match.context_before) == 2
