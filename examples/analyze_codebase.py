#!/usr/bin/env python3
"""
Example: Analyze a codebase using deepscroll.

This example shows how to use the RecursiveContextManager to analyze
a codebase of any size with natural language queries.

Usage:
    python analyze_codebase.py /path/to/codebase "How does authentication work?"
"""

import sys
from pathlib import Path

from deepscroll import RecursiveContextManager, DocumentNavigator


def load_codebase(path: str) -> list[str]:
    """Load all code files from a directory."""
    code_extensions = {
        ".py", ".js", ".ts", ".tsx", ".jsx",
        ".go", ".rs", ".java", ".c", ".cpp", ".h",
        ".md", ".txt", ".json", ".yaml", ".yml", ".toml",
    }

    skip_dirs = {
        "node_modules", ".git", "__pycache__",
        ".venv", "venv", "dist", "build", ".next",
    }

    p = Path(path)
    files: list[str] = []

    if p.is_file():
        content = p.read_text(encoding="utf-8", errors="replace")
        return [f"# File: {p.name}\n\n{content}"]

    for file in p.rglob("*"):
        if file.is_file() and file.suffix.lower() in code_extensions:
            # Skip unwanted directories
            if any(skip in str(file) for skip in skip_dirs):
                continue

            try:
                content = file.read_text(encoding="utf-8", errors="replace")
                rel_path = file.relative_to(p)
                files.append(f"# File: {rel_path}\n\n{content}")
            except Exception as e:
                print(f"Warning: Could not read {file}: {e}", file=sys.stderr)

    return files


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 3:
        print("Usage: python analyze_codebase.py <path> <query>")
        print("Example: python analyze_codebase.py ./src 'How does auth work?'")
        sys.exit(1)

    path = sys.argv[1]
    query = sys.argv[2]

    print(f"Loading codebase from: {path}")
    files = load_codebase(path)

    if not files:
        print(f"No code files found in: {path}")
        sys.exit(1)

    total_chars = sum(len(f) for f in files)
    print(f"Loaded {len(files)} files ({total_chars:,} characters)")

    print(f"\nQuery: {query}")
    print("\nAnalyzing...")

    # Create manager and analyze
    manager = RecursiveContextManager(
        llm="claude",  # or "openai"
        max_recursion=5,
    )

    result = manager.analyze(files, query)

    print("\n" + "=" * 60)
    print("RESULT")
    print("=" * 60)
    print(result)


if __name__ == "__main__":
    main()
