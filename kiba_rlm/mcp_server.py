"""
MCP Server for kiba-rlm - Claude Code integration.

Provides tools for recursive document analysis directly in Claude Code.

Uses OpenAI by default to avoid recursive API calls when running inside
Claude Code. Configure via environment variables:
  - OPENAI_API_KEY: Required for OpenAI models (default)
  - RLM_LLM_PROVIDER: "openai" (default) or "claude"
  - RLM_LLM_MODEL: Override model (default: gpt-5.4-nano)
  - RLM_MAX_TOKENS: Max output tokens per LLM call (default: 4096)
  - RLM_TEMPERATURE: Sampling temperature (default: 0.2)

Setup:
    Add to ~/.claude/mcp.json:
    {
      "mcpServers": {
        "kiba-rlm": {
          "command": "python",
          "args": ["-m", "kiba_rlm.mcp_server"],
          "env": {
            "OPENAI_API_KEY": "${OPENAI_API_KEY}",
            "RLM_LLM_MODEL": "gpt-5.4-nano",
            "RLM_MAX_TOKENS": "4096",
            "RLM_TEMPERATURE": "0.2"
          }
        }
      }
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

# LLM Configuration for RLM analysis
# Default to OpenAI GPT-5.4-nano to avoid recursive Claude API calls
RLM_LLM_PROVIDER = os.environ.get("RLM_LLM_PROVIDER", "openai")
RLM_LLM_MODEL = os.environ.get("RLM_LLM_MODEL", "gpt-5.4-mini")

# MCP imports - these will fail gracefully if not installed
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    MCP_AVAILABLE = True
except ImportError:
    MCP_AVAILABLE = False

from .core import RecursiveContextManager
from .llm import LLMInterface
from .navigator import DocumentNavigator

# Configure logging - use INFO level for MCP server
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Log configuration on startup
logger.info(f"kiba-rlm MCP Server initializing with provider={RLM_LLM_PROVIDER}, model={RLM_LLM_MODEL}")


def load_files_from_path(path: str, extensions: set[str] | None = None) -> list[str]:
    """Load all text files from a path."""
    if extensions is None:
        extensions = {
            ".txt", ".md", ".py", ".js", ".ts", ".tsx", ".jsx",
            ".json", ".yaml", ".yml", ".toml", ".rst", ".html",
            ".css", ".scss", ".go", ".rs", ".java", ".c", ".cpp",
            ".h", ".hpp", ".sh", ".bash", ".zsh", ".sql",
        }

    p = Path(path)
    files: list[str] = []

    if not p.exists():
        return files

    if p.is_file():
        try:
            content = p.read_text(encoding="utf-8", errors="replace")
            return [f"# File: {p.name}\n\n{content}"]
        except Exception:
            return files

    # Directory: recursive load
    for file in p.rglob("*"):
        if file.is_file() and file.suffix.lower() in extensions:
            # Skip common non-essential directories
            skip_dirs = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build"}
            if any(skip in str(file) for skip in skip_dirs):
                continue

            try:
                content = file.read_text(encoding="utf-8", errors="replace")
                rel_path = file.relative_to(p)
                files.append(f"# File: {rel_path}\n\n{content}")
            except Exception as e:
                logger.warning(f"Could not read {file}: {e}")

    return files


if MCP_AVAILABLE:
    server = Server("kiba-rlm")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        """List available tools."""
        return [
            Tool(
                name="analyze_codebase",
                description="""Analyze an entire codebase (any size) using recursive LLM navigation.

Uses the MIT RLM technique to process 10M+ tokens by treating code as external
variables and using LLM-generated navigation code.

Best for:
- Understanding large codebases
- Finding how features are implemented
- Tracing data flow across files
- Code review and architecture analysis""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to the codebase directory or file",
                        },
                        "query": {
                            "type": "string",
                            "description": "What you want to understand or find",
                        },
                    },
                    "required": ["path", "query"],
                },
            ),
            Tool(
                name="analyze_documents",
                description="""Analyze multiple large documents using recursive navigation.

Processes documents of any size by chunking and using LLM-guided search
to find relevant information efficiently.

Best for:
- Analyzing large PDFs, reports, or documentation
- Comparing information across multiple documents
- Finding specific information in large document sets
- Summarizing key points from extensive materials""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "paths": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of file paths to analyze",
                        },
                        "query": {
                            "type": "string",
                            "description": "Analysis query",
                        },
                    },
                    "required": ["paths", "query"],
                },
            ),
            Tool(
                name="deep_search",
                description="""Search through large document sets with context.

Uses recursive navigation to find and gather relevant sections,
providing comprehensive results even for vague queries.

Best for:
- Finding all mentions of a concept
- Gathering context around specific topics
- Understanding how a term is used across files""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to search in",
                        },
                        "pattern": {
                            "type": "string",
                            "description": "Search pattern (supports regex)",
                        },
                        "context_query": {
                            "type": "string",
                            "description": "Optional: question to answer using the search results",
                        },
                    },
                    "required": ["path", "pattern"],
                },
            ),
            Tool(
                name="document_stats",
                description="""Get statistics about a document set.

Returns file count, total size, token estimates, and file breakdown.""",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Path to analyze",
                        },
                    },
                    "required": ["path"],
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        """Handle tool calls."""
        try:
            if name == "analyze_codebase":
                return await analyze_codebase(
                    arguments["path"],
                    arguments["query"],
                )
            elif name == "analyze_documents":
                return await analyze_documents(
                    arguments["paths"],
                    arguments["query"],
                )
            elif name == "deep_search":
                return await deep_search(
                    arguments["path"],
                    arguments["pattern"],
                    arguments.get("context_query"),
                )
            elif name == "document_stats":
                return await document_stats(arguments["path"])
            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]
        except Exception as e:
            logger.exception(f"Error in tool {name}")
            return [TextContent(type="text", text=f"Error: {type(e).__name__}: {e}")]

    async def analyze_codebase(path: str, query: str) -> list[TextContent]:
        """Analyze a codebase using recursive navigation with lazy loading."""
        import time
        from pathlib import Path as PathLib
        from .file_index import FileIndex

        start_time = time.time()

        p = PathLib(path)
        if not p.exists():
            return [TextContent(type="text", text=f"Path not found: {path}")]

        # Build index first (only metadata, not content)
        logger.info(f"Building file index for: {path}")
        index = FileIndex(path)

        if index.file_count == 0:
            return [TextContent(type="text", text=f"No files found in: {path}")]

        index_time = time.time() - start_time
        logger.info(
            f"Indexed {index.file_count} files, "
            f"{index.total_size:,} bytes (~{index.estimated_tokens:,} tokens) "
            f"in {index_time:.2f}s"
        )

        # Run analysis in thread pool to not block
        def run_analysis() -> str:
            logger.info(f"Starting analysis with query: {query[:100]}...")
            manager = RecursiveContextManager(
                llm=RLM_LLM_PROVIDER,
                model=RLM_LLM_MODEL,
                max_recursion=8,
            )
            # Use the new path-based analysis that doesn't load all files
            return manager.analyze_path(path, query)

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, run_analysis)

        total_time = time.time() - start_time
        logger.info(f"Analysis completed in {total_time:.2f}s")

        response = f"""## Codebase Analysis

**Path:** {path}
**Files indexed:** {index.file_count}
**Total size:** {index.total_size:,} bytes (~{index.estimated_tokens:,} tokens)
**Analysis time:** {total_time:.1f}s

### Query
{query}

### Result
{result}
"""
        return [TextContent(type="text", text=response)]

    async def analyze_documents(paths: list[str], query: str) -> list[TextContent]:
        """Analyze multiple documents or directories."""
        from pathlib import Path as PathLib
        from .file_index import FileIndex

        total_files = 0
        total_size = 0

        # For multiple paths, we'll analyze each and combine results
        all_results = []

        for path in paths:
            p = PathLib(path)
            if not p.exists():
                continue

            if p.is_file():
                # Single file - read directly
                try:
                    content = p.read_text(encoding="utf-8", errors="replace")
                    total_files += 1
                    total_size += len(content)

                    def run_single(content=content) -> str:
                        manager = RecursiveContextManager(
                            llm=RLM_LLM_PROVIDER,
                            model=RLM_LLM_MODEL,
                            max_recursion=3,
                        )
                        return manager.analyze([f"# File: {p.name}\n\n{content}"], query)

                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(None, run_single)
                    all_results.append(f"### {p.name}\n{result}")
                except Exception as e:
                    all_results.append(f"### {p.name}\nError reading file: {e}")
            else:
                # Directory - use index-based analysis
                def run_dir(path=path) -> str:
                    manager = RecursiveContextManager(
                        llm=RLM_LLM_PROVIDER,
                        model=RLM_LLM_MODEL,
                        max_recursion=8,
                    )
                    return manager.analyze_path(path, query)

                index = FileIndex(path)
                total_files += index.file_count
                total_size += index.total_size

                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, run_dir)
                all_results.append(f"### {p.name}/\n{result}")

        if not all_results:
            return [TextContent(type="text", text=f"No documents found in paths: {paths}")]

        combined_result = "\n\n".join(all_results)

        response = f"""## Document Analysis

**Paths analyzed:** {len(paths)}
**Total files:** {total_files}
**Total size:** {total_size:,} bytes (~{total_size // 4:,} tokens)

### Query
{query}

### Results
{combined_result}
"""
        return [TextContent(type="text", text=response)]

    async def deep_search(
        path: str,
        pattern: str,
        context_query: str | None = None,
    ) -> list[TextContent]:
        """Deep search with optional context analysis using lazy loading."""
        from .file_index import FileIndex

        index = FileIndex(path)

        if index.file_count == 0:
            return [TextContent(type="text", text=f"No files found in: {path}")]

        # Use index-based grep (loads files on demand)
        matches = index.grep(pattern, max_matches=100, context_lines=3)

        if not matches:
            return [TextContent(type="text", text=f"No matches found for pattern: {pattern}")]

        # Format matches as sections
        sections = []
        for m in matches:
            sections.append(f"[{m['file']}:{m['line']}]\n{m['context']}\n")

        # If context query provided, analyze the sections
        if context_query:
            def run_analysis() -> str:
                manager = RecursiveContextManager(
                    llm=RLM_LLM_PROVIDER,
                    model=RLM_LLM_MODEL,
                    max_recursion=3,
                )
                return manager.analyze(sections, context_query)

            loop = asyncio.get_event_loop()
            analysis = await loop.run_in_executor(None, run_analysis)

            response = f"""## Deep Search Results

**Pattern:** `{pattern}`
**Matches found:** {len(matches)}

### Context Query
{context_query}

### Analysis
{analysis}

### Raw Matches (first 5)
{"".join(sections[:5])}
"""
        else:
            response = f"""## Search Results

**Pattern:** `{pattern}`
**Matches found:** {len(matches)}

### Matches
{"".join(sections[:10])}

{"*... and more matches*" if len(matches) > 10 else ""}
"""

        return [TextContent(type="text", text=response)]

    async def document_stats(path: str) -> list[TextContent]:
        """Get document statistics using file index (no content loading)."""
        from .file_index import FileIndex

        index = FileIndex(path)

        if index.file_count == 0:
            return [TextContent(type="text", text=f"No files found in: {path}")]

        # Get structure summary
        structure = index.get_structure_summary(max_depth=3)

        # File breakdown (just metadata, not content)
        files = index.get_file_list(max_files=30)
        breakdown = []
        for f in files:
            breakdown.append(f"- {f.size_bytes:,} bytes: {f.relative_path}")

        response = f"""## Document Statistics

**Path:** {path}
**Files:** {index.file_count}
**Total size:** {index.total_size:,} bytes
**Estimated tokens:** {index.estimated_tokens:,}

### Structure
{structure}

### File Breakdown (first 30)
{chr(10).join(breakdown)}

{"*... and more files*" if index.file_count > 30 else ""}
"""
        return [TextContent(type="text", text=response)]

    async def main() -> None:
        """Run the MCP server."""
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())


def run_server() -> None:
    """Entry point for running the server."""
    if not MCP_AVAILABLE:
        print("MCP package not installed. Install with: pip install mcp", file=sys.stderr)
        sys.exit(1)

    asyncio.run(main())


if __name__ == "__main__":
    run_server()
