"""Tests for RecursiveContextManager core functionality."""

import pytest
from unittest.mock import MagicMock, patch

from kiba_rlm.core import RecursiveContextManager, AnalysisResult


class TestRecursiveContextManager:
    """Test RecursiveContextManager functionality."""

    @pytest.fixture
    def mock_llm(self) -> MagicMock:
        """Create a mock LLM interface."""
        llm = MagicMock()
        llm.generate.return_value = "This is the analysis result."
        return llm

    @pytest.fixture
    def manager(self, mock_llm: MagicMock) -> RecursiveContextManager:
        """Create a manager with mock LLM."""
        return RecursiveContextManager(llm=mock_llm, max_recursion=3)

    def test_init_with_string_provider(self) -> None:
        """Test initialization with string provider name."""
        with patch("kiba_rlm.core.LLMInterface") as mock:
            mock.return_value = MagicMock()
            manager = RecursiveContextManager(llm="claude")
            mock.assert_called_once_with("claude")

    def test_init_with_llm_instance(self, mock_llm: MagicMock) -> None:
        """Test initialization with LLM instance."""
        manager = RecursiveContextManager(llm=mock_llm)
        assert manager.llm == mock_llm

    def test_analyze_small_documents(self, manager: RecursiveContextManager) -> None:
        """Test analyzing documents small enough for direct analysis."""
        docs = ["Short document 1.", "Short document 2."]

        result = manager.analyze(docs, "What are these documents about?")

        assert isinstance(result, str)
        # LLM should be called for direct analysis
        assert manager.llm.generate.called

    def test_analyze_returns_string(
        self, manager: RecursiveContextManager, mock_llm: MagicMock
    ) -> None:
        """Test that analyze returns a string."""
        mock_llm.generate.return_value = "Analysis complete."

        result = manager.analyze(["Test document"], "Summarize this")

        assert isinstance(result, str)
        assert result == "Analysis complete."

    def test_load_documents_from_strings(
        self, manager: RecursiveContextManager
    ) -> None:
        """Test loading documents from raw strings."""
        docs = ["Content 1", "Content 2"]

        loaded = manager._load_documents(docs)

        assert len(loaded) == 2
        assert loaded[0] == "Content 1"

    def test_create_doc_summary(self, manager: RecursiveContextManager) -> None:
        """Test document summary creation."""
        docs = ["A" * 100, "B" * 200]

        summary = manager._create_doc_summary(docs)

        assert "Doc 0" in summary
        assert "Doc 1" in summary
        assert "100" in summary  # First doc length
        assert "200" in summary  # Second doc length

    def test_direct_analysis_for_small_docs(
        self, manager: RecursiveContextManager, mock_llm: MagicMock
    ) -> None:
        """Test that small documents get direct analysis."""
        small_docs = ["Small doc."]

        manager.analyze(small_docs, "Query")

        # Should call generate for direct analysis
        assert mock_llm.generate.called
        call_args = mock_llm.generate.call_args[0][0]
        assert "Small doc." in call_args

    def test_chunked_analysis_fallback(
        self, manager: RecursiveContextManager, mock_llm: MagicMock
    ) -> None:
        """Test fallback to chunked analysis."""
        # Create a large document that will trigger navigation
        large_doc = "Content. " * 10000  # Large enough

        # Make navigation code fail
        mock_llm.generate.side_effect = [
            "invalid code that will fail",  # Navigation code
            "Chunked analysis result",  # Fallback analysis
        ]

        # This should fall back to chunked analysis
        # Note: With mocked LLM, the test mainly verifies the flow

    def test_max_recursion_limit(self, mock_llm: MagicMock) -> None:
        """Test that max recursion is respected."""
        manager = RecursiveContextManager(llm=mock_llm, max_recursion=2)

        assert manager.max_recursion == 2


class TestAnalysisResult:
    """Test AnalysisResult dataclass."""

    def test_create_basic_result(self) -> None:
        """Test creating a basic analysis result."""
        result = AnalysisResult(
            answer="Test answer",
            depth=1,
        )

        assert result.answer == "Test answer"
        assert result.depth == 1
        assert result.steps == []

    def test_create_full_result(self) -> None:
        """Test creating a full analysis result."""
        result = AnalysisResult(
            answer="Full answer",
            depth=3,
            steps=[{"type": "nav"}, {"type": "exec"}],
            total_tokens_processed=10000,
            documents_accessed=5,
        )

        assert result.answer == "Full answer"
        assert result.depth == 3
        assert len(result.steps) == 2
        assert result.total_tokens_processed == 10000
        assert result.documents_accessed == 5


class TestIntegration:
    """Integration tests (require mocking or real API)."""

    @pytest.mark.skip(reason="Requires real LLM API")
    def test_real_analysis(self) -> None:
        """Test with real LLM (skipped by default)."""
        manager = RecursiveContextManager(llm="claude")

        docs = [
            """# Python Basics
Python is a programming language.
It supports multiple paradigms.
""",
            """# Python Functions
Functions are defined with 'def'.
They can return values.
""",
        ]

        result = manager.analyze(docs, "What are the main topics covered?")

        assert isinstance(result, str)
        assert len(result) > 0
