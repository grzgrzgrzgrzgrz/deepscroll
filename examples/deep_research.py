#!/usr/bin/env python3
"""
Example: Deep research across multiple documents.

This example shows how to use deepscroll to analyze multiple documents
and synthesize information from them.

Usage:
    python deep_research.py doc1.md doc2.txt doc3.txt "What are the key findings?"
"""

import sys
from pathlib import Path

from deepscroll import RecursiveContextManager


def load_documents(paths: list[str]) -> list[str]:
    """Load documents from file paths."""
    documents: list[str] = []

    for path_str in paths:
        path = Path(path_str)

        if not path.exists():
            print(f"Warning: File not found: {path}", file=sys.stderr)
            continue

        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            documents.append(f"# Source: {path.name}\n\n{content}")
            print(f"Loaded: {path.name} ({len(content):,} chars)")
        except Exception as e:
            print(f"Warning: Could not read {path}: {e}", file=sys.stderr)

    return documents


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python deep_research.py <file1> [file2...] <query>")
        print("Example: python deep_research.py report.md notes.md 'Summarize key points'")
        sys.exit(1)

    # Last argument is the query
    query = sys.argv[-1]
    paths = sys.argv[1:-1]

    print("Loading documents...")
    documents = load_documents(paths)

    if not documents:
        print("No documents loaded.")
        sys.exit(1)

    total_chars = sum(len(d) for d in documents)
    print(f"\nLoaded {len(documents)} documents ({total_chars:,} total characters)")
    print(f"Query: {query}")
    print("\nAnalyzing...")

    # Create manager and analyze
    manager = RecursiveContextManager(
        llm="claude",  # or "openai"
        max_recursion=8,
        chunk_size=6000,  # Larger chunks for research
    )

    result = manager.analyze(documents, query)

    print("\n" + "=" * 60)
    print("RESEARCH RESULT")
    print("=" * 60)
    print(result)

    # Optionally save to file
    output_path = Path("research_result.md")
    output_path.write_text(f"# Research: {query}\n\n{result}")
    print(f"\nResult saved to: {output_path}")


if __name__ == "__main__":
    main()
