"""
FileIndex - Lazy-loading file index for large codebases.

Instead of loading all files into memory, we build an index with metadata
and load files on-demand when the LLM-generated code requests them.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator


@dataclass
class FileInfo:
    """Metadata about a file without loading its content."""

    path: Path
    relative_path: str
    size_bytes: int
    extension: str

    @property
    def size_kb(self) -> float:
        return self.size_bytes / 1024

    @property
    def estimated_tokens(self) -> int:
        """Rough estimate: 4 chars per token."""
        return self.size_bytes // 4


@dataclass
class DirectoryInfo:
    """Information about a directory."""

    path: Path
    relative_path: str
    file_count: int
    total_size: int
    subdirs: list[str] = field(default_factory=list)


class FileIndex:
    """
    Lazy-loading file index for large codebases.

    Key features:
    - Only stores file paths and metadata, not content
    - Loads file content on-demand
    - Provides directory structure overview
    - Supports filtering by extension, path pattern, etc.
    """

    SKIP_DIRS = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".next", ".cache", "coverage", ".nyc_output",
        ".pytest_cache", ".mypy_cache", "eggs", "*.egg-info",
    }

    CODE_EXTENSIONS = {
        ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java",
        ".c", ".cpp", ".h", ".hpp", ".cs", ".rb", ".php", ".swift",
        ".kt", ".scala", ".vue", ".svelte",
    }

    CONFIG_EXTENSIONS = {
        ".json", ".yaml", ".yml", ".toml", ".xml", ".ini", ".env",
        ".config", ".cfg",
    }

    DOC_EXTENSIONS = {
        ".md", ".txt", ".rst", ".adoc", ".html", ".css", ".scss",
    }

    ALL_EXTENSIONS = CODE_EXTENSIONS | CONFIG_EXTENSIONS | DOC_EXTENSIONS

    def __init__(
        self,
        root_path: str | Path,
        extensions: set[str] | None = None,
        max_file_size: int = 1_000_000,  # 1MB max per file
    ):
        """
        Initialize the file index.

        Args:
            root_path: Root directory to index
            extensions: File extensions to include (default: common code files)
            max_file_size: Maximum file size to index in bytes
        """
        self.root = Path(root_path).resolve()
        self.extensions = extensions or self.ALL_EXTENSIONS
        self.max_file_size = max_file_size

        self._files: dict[str, FileInfo] = {}
        self._dirs: dict[str, DirectoryInfo] = {}
        self._content_cache: dict[str, str] = {}

        self._build_index()

    def _should_skip_dir(self, path: Path) -> bool:
        """Check if directory should be skipped."""
        name = path.name
        return name in self.SKIP_DIRS or name.startswith(".")

    def _build_index(self) -> None:
        """Build the file index by walking the directory tree."""
        if not self.root.exists():
            return

        if self.root.is_file():
            self._index_file(self.root)
            return

        for dirpath, dirnames, filenames in os.walk(self.root):
            current = Path(dirpath)

            # Filter out directories to skip
            dirnames[:] = [d for d in dirnames if not self._should_skip_dir(current / d)]

            # Index files in this directory
            dir_files = 0
            dir_size = 0

            for filename in filenames:
                filepath = current / filename
                if filepath.suffix.lower() in self.extensions:
                    info = self._index_file(filepath)
                    if info:
                        dir_files += 1
                        dir_size += info.size_bytes

            # Store directory info
            rel_path = str(current.relative_to(self.root)) if current != self.root else "."
            self._dirs[rel_path] = DirectoryInfo(
                path=current,
                relative_path=rel_path,
                file_count=dir_files,
                total_size=dir_size,
                subdirs=dirnames.copy(),
            )

    def _index_file(self, filepath: Path) -> FileInfo | None:
        """Index a single file."""
        try:
            stat = filepath.stat()
            if stat.st_size > self.max_file_size:
                return None

            rel_path = str(filepath.relative_to(self.root))
            info = FileInfo(
                path=filepath,
                relative_path=rel_path,
                size_bytes=stat.st_size,
                extension=filepath.suffix.lower(),
            )
            self._files[rel_path] = info
            return info
        except (OSError, ValueError):
            return None

    # === Public API ===

    @property
    def file_count(self) -> int:
        """Total number of indexed files."""
        return len(self._files)

    @property
    def total_size(self) -> int:
        """Total size of all indexed files in bytes."""
        return sum(f.size_bytes for f in self._files.values())

    @property
    def estimated_tokens(self) -> int:
        """Estimated total tokens across all files."""
        return self.total_size // 4

    def get_structure_summary(self, max_depth: int = 3) -> str:
        """
        Get a compact summary of the directory structure.

        This is what the LLM sees first - just the structure, not content.
        """
        lines = [
            f"# Codebase: {self.root.name}",
            f"Total: {self.file_count} files, {self.total_size:,} bytes (~{self.estimated_tokens:,} tokens)",
            "",
            "## Directory Structure",
        ]

        def format_dir(rel_path: str, depth: int = 0) -> list[str]:
            if depth > max_depth:
                return []

            dir_info = self._dirs.get(rel_path)
            if not dir_info:
                return []

            indent = "  " * depth
            name = Path(rel_path).name if rel_path != "." else self.root.name
            result = [f"{indent}- {name}/ ({dir_info.file_count} files, {dir_info.total_size:,} bytes)"]

            for subdir in sorted(dir_info.subdirs)[:10]:  # Limit subdirs shown
                sub_path = f"{rel_path}/{subdir}" if rel_path != "." else subdir
                result.extend(format_dir(sub_path, depth + 1))

            if len(dir_info.subdirs) > 10:
                result.append(f"{indent}  ... and {len(dir_info.subdirs) - 10} more directories")

            return result

        lines.extend(format_dir("."))
        return "\n".join(lines)

    def get_file_list(
        self,
        directory: str = ".",
        pattern: str | None = None,
        extensions: set[str] | None = None,
        max_files: int = 100,
    ) -> list[FileInfo]:
        """
        Get list of files, optionally filtered.

        Args:
            directory: Directory to list (relative to root)
            pattern: Glob pattern to match filenames
            extensions: Filter by extensions
            max_files: Maximum files to return
        """
        results = []

        for rel_path, info in self._files.items():
            # Check directory
            if directory != ".":
                if not rel_path.startswith(directory + "/") and rel_path != directory:
                    continue

            # Check pattern
            if pattern:
                import fnmatch
                if not fnmatch.fnmatch(info.path.name, pattern):
                    continue

            # Check extensions
            if extensions and info.extension not in extensions:
                continue

            results.append(info)

            if len(results) >= max_files:
                break

        return sorted(results, key=lambda f: f.relative_path)

    def read_file(self, relative_path: str) -> str | None:
        """
        Read file content (lazy loading with caching).

        Args:
            relative_path: Path relative to root

        Returns:
            File content or None if not found/readable
        """
        # Check cache first
        if relative_path in self._content_cache:
            return self._content_cache[relative_path]

        info = self._files.get(relative_path)
        if not info:
            return None

        try:
            content = info.path.read_text(encoding="utf-8", errors="replace")
            # Cache for reuse (limit cache size)
            if len(self._content_cache) < 100:
                self._content_cache[relative_path] = content
            return content
        except Exception:
            return None

    def read_files(self, paths: list[str]) -> dict[str, str]:
        """Read multiple files at once."""
        return {p: content for p in paths if (content := self.read_file(p)) is not None}

    def search_filenames(self, query: str, max_results: int = 50) -> list[FileInfo]:
        """
        Search for files by name.

        Args:
            query: Search query (case-insensitive substring match)
            max_results: Maximum results

        Returns:
            List of matching FileInfo objects
        """
        query_lower = query.lower()
        results = []

        for rel_path, info in self._files.items():
            if query_lower in rel_path.lower():
                results.append(info)
                if len(results) >= max_results:
                    break

        return results

    def grep(
        self,
        pattern: str,
        directory: str = ".",
        max_matches: int = 50,
        context_lines: int = 2,
    ) -> list[dict]:
        """
        Search file contents for a pattern (loads files on demand).

        Args:
            pattern: Regex pattern to search
            directory: Directory to search in
            max_matches: Maximum matches to return
            context_lines: Lines of context around match

        Returns:
            List of match dictionaries
        """
        import re

        try:
            regex = re.compile(pattern, re.IGNORECASE)
        except re.error:
            return []

        matches = []
        files = self.get_file_list(directory, max_files=500)

        for file_info in files:
            content = self.read_file(file_info.relative_path)
            if not content:
                continue

            lines = content.split("\n")
            for line_num, line in enumerate(lines, 1):
                if regex.search(line):
                    # Get context
                    start = max(0, line_num - context_lines - 1)
                    end = min(len(lines), line_num + context_lines)
                    context = lines[start:end]

                    matches.append({
                        "file": file_info.relative_path,
                        "line": line_num,
                        "content": line.strip(),
                        "context": "\n".join(context),
                    })

                    if len(matches) >= max_matches:
                        return matches

        return matches

    def get_file_preview(self, relative_path: str, max_lines: int = 50) -> str | None:
        """Get first N lines of a file."""
        content = self.read_file(relative_path)
        if not content:
            return None

        lines = content.split("\n")[:max_lines]
        preview = "\n".join(lines)

        if len(content.split("\n")) > max_lines:
            preview += f"\n\n... ({len(content.split(chr(10))) - max_lines} more lines)"

        return preview
