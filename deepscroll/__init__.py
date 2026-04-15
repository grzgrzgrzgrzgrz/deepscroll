"""
deepscroll: Recursive Language Models for Infinite Context

Implements MIT RLM paper techniques for 10M+ token context analysis.
Treats documents as external variables, uses LLM-generated code to navigate.

Example:
    from deepscroll import analyze_codebase, analyze_large_context

    # Analyze a codebase (recommended for large projects)
    result = analyze_codebase("/path/to/project", "How does authentication work?")

    # Or analyze specific documents
    result = analyze_large_context(
        documents=["doc1.txt", "doc2.md"],
        query="What are the key themes across all documents?"
    )
"""

from .core import RecursiveContextManager
from .file_index import FileIndex
from .llm import LLMInterface
from .navigator import DocumentNavigator
from .repl import SecurePythonREPL

__version__ = "0.1.0"
__all__ = [
    "RecursiveContextManager",
    "SecurePythonREPL",
    "DocumentNavigator",
    "LLMInterface",
    "FileIndex",
    "analyze_large_context",
    "analyze_codebase",
]


def analyze_large_context(
    documents: list[str],
    query: str,
    llm: str = "openai",
    model: str | None = None,
    max_recursion: int = 10,
) -> str:
    """
    Analyze arbitrarily large documents (10M+ tokens) using Recursive Language Model techniques.

    Args:
        documents: List of document contents or file paths
        query: The analysis query
        llm: LLM provider ("claude" or "openai", default: openai)
        model: Specific model (e.g., "gpt-4o-mini", "claude-sonnet-4-20250514")
        max_recursion: Maximum recursive depth for analysis

    Returns:
        Analysis result as string
    """
    manager = RecursiveContextManager(llm=llm, model=model, max_recursion=max_recursion)
    return manager.analyze(documents, query)


def analyze_codebase(
    path: str,
    query: str,
    llm: str = "openai",
    model: str | None = None,
    max_recursion: int = 8,
) -> str:
    """
    Analyze a codebase of any size using lazy-loading file index.

    This is the recommended method for large codebases (10M+ tokens).
    Files are only loaded on-demand as the LLM explores.

    Args:
        path: Path to the codebase directory
        query: What you want to understand or find
        llm: LLM provider ("claude" or "openai", default: openai)
        model: Specific model (e.g., "gpt-4o-mini")
        max_recursion: Maximum recursive depth

    Returns:
        Analysis result as string
    """
    manager = RecursiveContextManager(llm=llm, model=model, max_recursion=max_recursion)
    return manager.analyze_path(path, query)
