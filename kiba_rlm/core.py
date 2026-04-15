"""
RecursiveContextManager - Core implementation of MIT RLM paper techniques.

Implements the key insight: treat documents as external variables that the LLM
can access via code execution, enabling analysis of arbitrarily large contexts.

IMPORTANT: Files are NOT loaded into context. Instead:
1. LLM sees only file structure/index
2. LLM generates code to navigate and search
3. Code execution loads files on-demand
4. Results are synthesized from targeted exploration
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .llm import LLMInterface
from .navigator import DocumentNavigator
from .repl import SecurePythonREPL, REPLResult
from .file_index import FileIndex

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """Result of a recursive analysis."""

    answer: str
    depth: int
    steps: list[dict[str, Any]] = field(default_factory=list)
    total_tokens_processed: int = 0
    documents_accessed: int = 0


@dataclass
class SubAnalysisRequest:
    """Request for deeper analysis on a subset of documents."""

    subdocs: list[str]
    subquery: str
    reason: str


class RecursiveContextManager:
    """
    Manages recursive analysis of large document sets using LLM-generated code.

    The key technique from the MIT RLM paper:
    1. Load documents as external variables (not in context)
    2. LLM generates Python code to navigate/search documents
    3. Execute code in secure sandbox
    4. Recursively drill down into relevant sections
    5. Synthesize final answer from gathered information

    This enables processing of 10M+ tokens without context window limits.
    """

    def __init__(
        self,
        llm: str | LLMInterface = "claude",
        model: str | None = None,
        max_recursion: int = 10,
        chunk_size: int = 4000,
        overlap: int = 200,
    ):
        """
        Initialize the RecursiveContextManager.

        Args:
            llm: LLM provider name or LLMInterface instance
            model: Specific model to use (e.g., "gpt-4o-mini")
            max_recursion: Maximum recursive depth
            chunk_size: Size of text chunks for processing
            overlap: Overlap between chunks
        """
        self.llm = LLMInterface(llm, model=model) if isinstance(llm, str) else llm
        self.max_recursion = max_recursion
        self.chunk_size = chunk_size
        self.overlap = overlap
        self.navigator = DocumentNavigator(chunk_size=chunk_size, overlap=overlap)
        self.repl = SecurePythonREPL()

    def analyze(
        self,
        documents: list[str],
        query: str,
        depth: int = 0,
    ) -> str:
        """
        Analyze documents using recursive LLM-guided navigation.

        Args:
            documents: List of document contents or file paths
            query: The analysis query
            depth: Current recursion depth (internal use)

        Returns:
            Analysis result as string
        """
        result = self._analyze_internal(documents, query, depth)
        return result.answer

    def analyze_path(self, path: str, query: str) -> str:
        """
        Analyze a file path (file or directory) using lazy-loading index.

        This is the preferred method for large codebases - it doesn't load
        all files into memory, but navigates through them on-demand.

        Args:
            path: Path to file or directory
            query: The analysis query

        Returns:
            Analysis result as string
        """
        # Build file index (only metadata, not content)
        index = FileIndex(path)

        logger.info(
            f"Indexing {path}: {index.file_count} files, "
            f"{index.total_size:,} bytes (~{index.estimated_tokens:,} tokens)"
        )

        # For small codebases, use direct analysis
        if index.estimated_tokens < 50_000:
            logger.info("Small codebase - using direct analysis")
            # Load all files and use traditional analysis
            docs = []
            for file_info in index.get_file_list(max_files=200):
                content = index.read_file(file_info.relative_path)
                if content:
                    docs.append(f"# File: {file_info.relative_path}\n\n{content}")
            return self.analyze(docs, query)

        # For large codebases, use index-based navigation
        logger.info("Large codebase - using index-based navigation")
        return self._analyze_with_index(index, query)

    def _analyze_with_index(self, index: FileIndex, query: str) -> str:
        """
        Analyze using file index - the core RLM approach.

        The LLM sees:
        1. Directory structure overview
        2. Available navigation functions
        3. The query

        Then generates code to explore and find relevant information.
        """
        steps: list[dict[str, Any]] = []

        # Set up REPL with index access
        self._setup_repl_with_index(index)

        # Generate exploration code
        structure = index.get_structure_summary(max_depth=3)

        # Try up to 3 times to get a valid result
        max_attempts = 3
        result_var = None
        last_error = None

        for attempt in range(max_attempts):
            try:
                nav_code = self._generate_index_navigation_code(structure, query, index.file_count)
                steps.append({"type": "navigation_code", "attempt": attempt + 1, "code": nav_code})

                logger.info(f"Navigation attempt {attempt + 1}: executing generated code ({len(nav_code)} chars)")

                # Execute navigation
                repl_result = self.repl.execute(nav_code)
                steps.append({
                    "type": "repl_execution",
                    "attempt": attempt + 1,
                    "success": repl_result.success,
                    "output": repl_result.output[:2000] if repl_result.output else None,
                    "error": repl_result.error,
                })

                if not repl_result.success:
                    last_error = repl_result.error
                    logger.warning(f"Navigation attempt {attempt + 1} failed: {repl_result.error}")
                    # Reset for next attempt
                    self._setup_repl_with_index(index)
                    continue

                # Get the result variable
                result_var = self.repl.get_variable("result")

                # Check if we got a meaningful result
                if result_var and str(result_var).strip() and str(result_var) != "None":
                    result_str = str(result_var)
                    if len(result_str) > 50:  # Meaningful result
                        logger.info(f"Got result with {len(result_str)} chars on attempt {attempt + 1}")
                        break
                    else:
                        logger.warning(f"Result too short ({len(result_str)} chars), retrying...")
                else:
                    logger.warning(f"No result on attempt {attempt + 1}, retrying...")

                # Reset for next attempt
                self._setup_repl_with_index(index)

            except Exception as e:
                last_error = str(e)
                logger.error(f"Exception on attempt {attempt + 1}: {e}")
                self._setup_repl_with_index(index)

        # If still no result, use fallback
        if not result_var or not str(result_var).strip() or str(result_var) == "None" or len(str(result_var)) < 50:
            logger.info(f"Navigation produced no results (last error: {last_error}), using fallback grep-based analysis")
            return self._fallback_analysis(index, query)

        result_str = str(result_var)

        # Check if we need deeper analysis
        if len(result_str) > 10000:
            # Result is large - need to analyze it further
            logger.info(f"Result is large ({len(result_str)} chars), running deeper analysis")
            deeper_result = self._analyze_deep_result(result_str, query)
            return deeper_result

        # Synthesize answer from exploration results
        answer = self._synthesize_from_exploration(repl_result, result_var, query)
        return answer

    def _setup_repl_with_index(self, index: FileIndex) -> None:
        """Set up REPL environment with index-based navigation functions."""
        self.repl.reset()

        # Store index reference
        self.repl.set_variable("fileindex", index)

        # Add navigation functions
        helpers = '''
# Navigation functions for exploring the codebase

def list_files(directory=".", pattern=None, max_files=50):
    """List files in a directory.

    Args:
        directory: Directory path relative to root (use "." for root)
        pattern: Optional glob pattern (e.g., "*.tsx", "test_*")
        max_files: Maximum files to return

    Returns:
        List of dicts with file info (path, size, extension)
    """
    files = fileindex.get_file_list(directory, pattern, max_files=max_files)
    return [{"path": f.relative_path, "size": f.size_bytes, "ext": f.extension} for f in files]

def read_file(path):
    """Read a file's content.

    Args:
        path: Relative path to file

    Returns:
        File content as string, or None if not found
    """
    return fileindex.read_file(path)

def preview_file(path, max_lines=50):
    """Get first N lines of a file.

    Args:
        path: Relative path to file
        max_lines: Maximum lines to return

    Returns:
        Preview string or None
    """
    return fileindex.get_file_preview(path, max_lines)

def search_files(query, max_results=30):
    """Search for files by name.

    Args:
        query: Search string (matches anywhere in path)
        max_results: Maximum results

    Returns:
        List of matching file paths
    """
    files = fileindex.search_filenames(query, max_results)
    return [f.relative_path for f in files]

def grep(pattern, directory=".", max_matches=30):
    """Search file contents for a regex pattern.

    Args:
        pattern: Regex pattern to search
        directory: Directory to search in
        max_matches: Maximum matches

    Returns:
        List of dicts with file, line, content, context
    """
    return fileindex.grep(pattern, directory, max_matches)

def get_structure():
    """Get directory structure overview."""
    return fileindex.get_structure_summary(max_depth=4)

# Store results in this variable
result = None
'''
        self.repl.execute(helpers)

    def _generate_index_navigation_code(
        self,
        structure: str,
        query: str,
        file_count: int,
    ) -> str:
        """Generate code to explore the codebase index."""
        prompt = f"""You are a code explorer. Search this codebase ({file_count} files) to answer a query.

## Directory Structure
{structure}

## Available Functions
- search_files(query) - Find files by name. Returns list of paths: ["path/to/file.tsx", ...]
- grep(pattern, max_matches=30) - Search file contents with regex. Returns: [{{"file": "...", "line": 42, "content": "...", "context": "..."}}]
- list_files(directory=".", pattern=None, max_files=50) - List files in a directory. Returns: [{{"path": "...", "size": 1234}}]
- read_file(path) - Read a file's content. Returns string or None
- preview_file(path, max_lines=50) - Get first N lines of a file

## Query
{query}

## IMPORTANT RULES
1. You MUST set the `result` variable with your findings
2. Start with grep() to find relevant code, then read_file() for details
3. Collect findings in a list, then join them for result
4. Use string concatenation with + instead of f-strings for complex strings
5. Always check if content is not None before using it

## Example Code
```python
# Step 1: Search for relevant code
matches = grep("authentication|login|auth", max_matches=25)

# Step 2: Get unique files
relevant_files = []
seen = set()
for m in matches:
    if m["file"] not in seen:
        relevant_files.append(m["file"])
        seen.add(m["file"])

# Step 3: Read and collect content from top files
findings = []
for filepath in relevant_files[:5]:
    content = read_file(filepath)
    if content:
        # Truncate long files
        if len(content) > 2000:
            content = content[:2000] + "\\n... (truncated)"
        findings.append("## " + filepath + "\\n```\\n" + content + "\\n```")

# Step 4: Set result (REQUIRED!)
if findings:
    result = "\\n\\n".join(findings)
else:
    result = "No relevant files found for the query."
```

Now write Python code to answer the query. Output ONLY code, no explanations:"""

        code = self.llm.generate(prompt, max_tokens=2000, temperature=0.2)

        # Clean up code
        code = code.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]

        return code.strip()

    def _fallback_analysis(self, index: FileIndex, query: str) -> str:
        """Fallback when navigation fails - smart multi-strategy search."""
        logger.info("Using fallback multi-strategy analysis")

        # Extract keywords from query
        keywords = self._extract_keywords(query)
        logger.info(f"Extracted keywords: {keywords}")

        all_findings: list[dict] = []
        files_with_content: dict[str, str] = {}
        seen_files: set[str] = set()

        # Strategy 1: Search with keywords
        for keyword in keywords[:7]:
            matches = index.grep(keyword, max_matches=15)
            for m in matches:
                if m["file"] not in seen_files:
                    all_findings.append(m)
                    seen_files.add(m["file"])

        # Strategy 2: Search filenames
        for keyword in keywords[:5]:
            file_matches = index.search_filenames(keyword, max_results=10)
            for f in file_matches:
                if f.relative_path not in files_with_content and f.relative_path not in seen_files:
                    content = index.read_file(f.relative_path)
                    if content:
                        files_with_content[f.relative_path] = content[:3000]

        # Strategy 3: If nothing found, try common code patterns
        if not all_findings and not files_with_content:
            # Try common patterns based on query type
            common_patterns = ["function", "class", "export", "import", "def ", "const "]
            for pattern in common_patterns:
                matches = index.grep(pattern, max_matches=10)
                if matches:
                    for m in matches:
                        if m["file"] not in seen_files:
                            all_findings.append(m)
                            seen_files.add(m["file"])
                    break

        # Strategy 4: If still nothing, get some representative files
        if not all_findings and not files_with_content:
            # Get some key files
            for pattern in ["README", "index", "main", "app", "config"]:
                files = index.search_filenames(pattern, max_results=3)
                for f in files:
                    if f.relative_path not in files_with_content:
                        content = index.read_file(f.relative_path)
                        if content:
                            files_with_content[f.relative_path] = content[:2000]
                if files_with_content:
                    break

        if not all_findings and not files_with_content:
            return f"Keine relevanten Informationen für '{query}' gefunden. Die Codebase enthält {index.file_count} Dateien. Versuche eine spezifischere Suche mit konkreten Dateinamen oder Funktionsnamen."

        # Format findings
        findings_parts = []

        # Add grep matches (show context)
        for match in all_findings[:20]:
            findings_parts.append(f"### {match['file']}:{match['line']}\n```\n{match['context']}\n```")

        # Add file content for filename matches
        for filepath, content in list(files_with_content.items())[:5]:
            findings_parts.append(f"### {filepath}\n```\n{content}\n```")

        findings_text = "\n\n".join(findings_parts)
        logger.info(f"Fallback found {len(all_findings)} grep matches + {len(files_with_content)} files")

        # Synthesize answer
        return self._synthesize_from_findings(findings_text, query)

    def _extract_keywords(self, query: str) -> list[str]:
        """Extract search keywords from query - improved version."""
        import re

        # Common stopwords in multiple languages
        stopwords = {
            'the', 'and', 'for', 'this', 'that', 'what', 'how', 'why', 'where', 'when',
            'which', 'who', 'with', 'from', 'into', 'about', 'are', 'was', 'were', 'been',
            'being', 'have', 'has', 'had', 'does', 'did', 'will', 'would', 'could', 'should',
            'the', 'ist', 'die', 'der', 'das', 'und', 'oder', 'für', 'mit', 'von', 'aus',
            'wie', 'was', 'wer', 'welche', 'welcher', 'diese', 'dieser', 'dieses', 'eine',
            'einer', 'einem', 'einen', 'kann', 'sind', 'wird', 'werden', 'wurde', 'wurden',
            'beschreibe', 'erkläre', 'zeige', 'finde', 'suche', 'describe', 'explain', 'show',
            'find', 'search', 'gibt', 'gibt', 'macht', 'machen', 'does', 'make', 'makes'
        }

        # Extract words (including CamelCase parts)
        words = re.findall(r'\b[A-Za-z][A-Za-z0-9_-]{2,}\b', query)

        # Also extract CamelCase components
        camel_parts = []
        for word in words:
            parts = re.findall(r'[A-Z][a-z]+|[a-z]+', word)
            camel_parts.extend([p for p in parts if len(p) > 2])

        all_words = words + camel_parts

        # Filter and prioritize
        keywords = []
        seen = set()
        for w in all_words:
            w_lower = w.lower()
            if w_lower not in stopwords and w_lower not in seen and len(w) > 2:
                keywords.append(w)
                seen.add(w_lower)

        # Sort by length (longer = more specific = better)
        keywords.sort(key=len, reverse=True)

        return keywords[:10]

    def _analyze_deep_result(self, result_text: str, query: str) -> str:
        """Analyze a large result by summarizing it."""
        prompt = f"""Analyze these code exploration results to answer the query.

## Results from Codebase Exploration
{result_text[:12000]}

## Query
{query}

Provide a comprehensive answer based on the exploration results."""

        return self.llm.generate(prompt, max_tokens=2000)

    def _synthesize_from_exploration(
        self,
        repl_result: REPLResult,
        result_var: Any,
        query: str,
    ) -> str:
        """Synthesize answer from exploration results."""
        context = str(result_var) if result_var else (repl_result.output or "No results")

        prompt = f"""You are analyzing code exploration results. Answer the query based on the actual code found.

## Code Found During Exploration
{context[:12000]}

## Original Query
{query}

## Instructions
1. Answer based ONLY on the code shown above
2. Include relevant code snippets in your answer
3. Explain what the code does
4. If the code shows components, describe their purpose and props
5. Be specific - reference actual file names, function names, component names
6. Format your answer clearly with headers and code blocks

Provide a comprehensive technical answer:"""

        return self.llm.generate(prompt, max_tokens=2500)

    def _synthesize_from_findings(self, findings: str, query: str) -> str:
        """Synthesize answer from grep findings."""
        prompt = f"""You are analyzing code search results. Answer the query based on the actual code found.

## Search Results (file:line followed by code context)
{findings[:12000]}

## Original Query
{query}

## Instructions
1. Answer based ONLY on the actual code shown above
2. Include the most relevant code snippets
3. Explain what each relevant file/function does
4. Reference specific file paths and line numbers
5. If you see imports, components, or functions - explain their purpose
6. Be technical and specific

Provide a clear, well-structured answer:"""

        return self.llm.generate(prompt, max_tokens=2500)

    # === Legacy methods for backward compatibility ===

    def _analyze_internal(
        self,
        documents: list[str],
        query: str,
        depth: int = 0,
    ) -> AnalysisResult:
        """Internal analysis with full result tracking - for pre-loaded documents."""
        steps: list[dict[str, Any]] = []

        # Load documents (resolve file paths if needed)
        loaded_docs = self._load_documents(documents)
        total_chars = sum(len(d) for d in loaded_docs)

        logger.info(
            f"Analyzing {len(loaded_docs)} documents ({total_chars:,} chars) at depth {depth}"
        )

        # Check if small enough to analyze directly (up to ~30k chars / ~7.5k tokens)
        if total_chars < 30_000:
            return self._direct_analysis(loaded_docs, query, depth, steps)

        # For medium-sized sets, use chunked analysis
        if total_chars < 100_000:  # ~25k tokens
            return self._chunked_analysis(loaded_docs, query, depth, steps)

        # For larger sets, use navigation
        self._setup_repl_environment(loaded_docs)
        nav_code = self._generate_navigation_code(loaded_docs, query)
        steps.append({"type": "navigation_code", "code": nav_code})

        repl_result = self.repl.execute(nav_code)
        steps.append({
            "type": "repl_execution",
            "success": repl_result.success,
            "output": repl_result.output[:1000] if repl_result.output else None,
            "error": repl_result.error,
        })

        if not repl_result.success:
            logger.warning(f"Navigation failed: {repl_result.error}. Falling back to chunked.")
            return self._chunked_analysis(loaded_docs, query, depth, steps)

        # Check if we need to go deeper
        sub_request = self._check_for_sub_analysis(repl_result, query)

        if sub_request and depth < self.max_recursion:
            steps.append({
                "type": "sub_analysis_requested",
                "reason": sub_request.reason,
                "subdocs_count": len(sub_request.subdocs),
            })

            sub_result = self._analyze_internal(
                sub_request.subdocs,
                sub_request.subquery,
                depth + 1,
            )
            steps.extend(sub_result.steps)

            return AnalysisResult(
                answer=sub_result.answer,
                depth=depth + 1,
                steps=steps,
                total_tokens_processed=sub_result.total_tokens_processed,
                documents_accessed=sub_result.documents_accessed + len(loaded_docs),
            )

        answer = self._synthesize_answer(repl_result, query)
        steps.append({"type": "synthesis", "answer_length": len(answer)})

        return AnalysisResult(
            answer=answer,
            depth=depth,
            steps=steps,
            total_tokens_processed=total_chars // 4,
            documents_accessed=len(loaded_docs),
        )

    def _load_documents(self, documents: list[str]) -> list[str]:
        """Load documents from file paths or return raw content."""
        loaded = []
        for doc in documents:
            path = Path(doc)
            if path.exists() and path.is_file():
                try:
                    content = path.read_text(encoding="utf-8")
                    loaded.append(content)
                except Exception as e:
                    logger.warning(f"Failed to read {path}: {e}")
                    loaded.append(doc)
            else:
                loaded.append(doc)
        return loaded

    def _setup_repl_environment(self, documents: list[str]) -> None:
        """Set up the REPL with documents and navigation tools."""
        self.repl.reset()
        self.repl.set_variable("docs", documents)
        self.repl.set_variable("nav", self.navigator)

        helpers = """
def search(pattern, docs=docs):
    '''Search all documents for a pattern, return matching sections.'''
    return nav.grep(docs, pattern)

def get_chunk(doc_idx, chunk_idx, docs=docs):
    '''Get a specific chunk from a document.'''
    chunks = nav.chunk(docs[doc_idx])
    if 0 <= chunk_idx < len(chunks):
        return chunks[chunk_idx]
    return None

def summarize_doc(doc_idx, docs=docs):
    '''Get first and last chunks of a document for overview.'''
    chunks = nav.chunk(docs[doc_idx])
    if len(chunks) <= 2:
        return '\\n'.join(chunks)
    return f"START:\\n{chunks[0]}\\n\\n...\\n\\nEND:\\n{chunks[-1]}"

def doc_stats(docs=docs):
    '''Get statistics about all documents.'''
    return {
        'count': len(docs),
        'lengths': [len(d) for d in docs],
        'total_chars': sum(len(d) for d in docs),
    }
"""
        self.repl.execute(helpers)

    def _generate_navigation_code(self, documents: list[str], query: str) -> str:
        """Generate Python code to navigate documents based on query."""
        # Create COMPACT summary - just file count and total size, not content
        doc_count = len(documents)
        total_size = sum(len(d) for d in documents)

        # Only show first few doc previews
        previews = []
        for i, doc in enumerate(documents[:10]):
            preview = doc[:200].replace("\n", " ")[:100]
            previews.append(f"Doc {i}: {len(doc):,} chars - {preview}...")

        if doc_count > 10:
            previews.append(f"... and {doc_count - 10} more documents")

        doc_summary = "\n".join(previews)

        prompt = f"""You have {doc_count} documents ({total_size:,} chars) stored in `docs`.

Document previews:
{doc_summary}

Available functions:
- search(pattern) - Search all docs for regex pattern
- get_chunk(doc_idx, chunk_idx) - Get specific chunk
- summarize_doc(doc_idx) - Get overview of a document
- doc_stats() - Get document statistics
- len(docs), docs[i] - Access documents directly

Query: {query}

Write Python code to find relevant information. Store findings in `result`.
Be efficient - use search() first, then examine specific docs.
Only output Python code."""

        code = self.llm.generate(prompt, max_tokens=1000)

        code = code.strip()
        if code.startswith("```python"):
            code = code[9:]
        if code.startswith("```"):
            code = code[3:]
        if code.endswith("```"):
            code = code[:-3]

        return code.strip()

    def _create_doc_summary(self, documents: list[str]) -> str:
        """Create a COMPACT summary of documents for the LLM."""
        # IMPORTANT: Only show first few, not all!
        summaries = []
        for i, doc in enumerate(documents[:5]):
            preview = doc[:300].replace("\n", " ")[:150]
            summaries.append(f"Doc {i}: {len(doc):,} chars - {preview}...")

        if len(documents) > 5:
            summaries.append(f"... and {len(documents) - 5} more documents")

        return "\n".join(summaries)

    def _check_for_sub_analysis(
        self,
        repl_result: REPLResult,
        query: str,
    ) -> SubAnalysisRequest | None:
        """Check if we need deeper analysis on a subset of documents."""
        if not repl_result.success or not repl_result.output:
            return None

        result_var = self.repl.get_variable("result")
        if result_var is None:
            return None

        result_str = str(result_var)

        if len(result_str) > self.chunk_size * 3:
            prompt = f"""Given this search result:

{result_str[:2000]}...

And the query: {query}

Need deeper analysis? Respond with JSON:
{{"need_deeper": true/false, "subdocs": ["relevant sections"], "subquery": "refined query"}}"""

            response = self.llm.generate(prompt, max_tokens=500)

            try:
                response = response.strip()
                if response.startswith("```"):
                    response = response.split("```")[1]
                    if response.startswith("json"):
                        response = response[4:]

                data = json.loads(response.strip())
                if data.get("need_deeper") and data.get("subdocs"):
                    return SubAnalysisRequest(
                        subdocs=data["subdocs"],
                        subquery=data.get("subquery", query),
                        reason="Large result set requires deeper analysis",
                    )
            except (json.JSONDecodeError, KeyError):
                pass

        return None

    def _direct_analysis(
        self,
        documents: list[str],
        query: str,
        depth: int,
        steps: list[dict[str, Any]],
    ) -> AnalysisResult:
        """Directly analyze small document set without navigation."""
        combined = "\n\n---\n\n".join(documents)
        steps.append({"type": "direct_analysis", "total_chars": len(combined)})

        prompt = f"""Analyze these documents to answer the query.

Documents:
{combined}

Query: {query}

Provide a comprehensive, detailed answer based on the document content above."""

        answer = self.llm.generate(prompt)

        return AnalysisResult(
            answer=answer,
            depth=depth,
            steps=steps,
            total_tokens_processed=len(combined) // 4,
            documents_accessed=len(documents),
        )

    def _chunked_analysis(
        self,
        documents: list[str],
        query: str,
        depth: int,
        steps: list[dict[str, Any]],
    ) -> AnalysisResult:
        """Analyze documents in chunks and synthesize."""
        all_chunks = []
        for doc in documents:
            all_chunks.extend(self.navigator.chunk(doc))

        steps.append({"type": "chunked_analysis", "chunk_count": len(all_chunks)})

        findings = []
        batch_size = 5

        for i in range(0, len(all_chunks), batch_size):
            batch = all_chunks[i : i + batch_size]
            batch_text = "\n\n---\n\n".join(batch)

            prompt = f"""Extract relevant info for the query from these chunks.

Chunks:
{batch_text}

Query: {query}

If no relevant info, say "NO_RELEVANT_INFO". Otherwise summarize findings."""

            response = self.llm.generate(prompt, max_tokens=500)
            if "NO_RELEVANT_INFO" not in response:
                findings.append(response)

        if not findings:
            return AnalysisResult(
                answer="No relevant information found in the documents.",
                depth=depth,
                steps=steps,
                total_tokens_processed=sum(len(c) for c in all_chunks) // 4,
                documents_accessed=len(documents),
            )

        combined_findings = "\n\n".join(findings)
        answer = self._synthesize_findings(combined_findings, query)

        return AnalysisResult(
            answer=answer,
            depth=depth,
            steps=steps,
            total_tokens_processed=sum(len(c) for c in all_chunks) // 4,
            documents_accessed=len(documents),
        )

    def _synthesize_answer(self, repl_result: REPLResult, query: str) -> str:
        """Synthesize final answer from REPL result."""
        result_var = self.repl.get_variable("result")
        context = str(result_var) if result_var else repl_result.output

        prompt = f"""Based on these analysis results, answer the query.

Results:
{context[:8000]}

Query: {query}

Provide a clear, well-structured answer."""

        return self.llm.generate(prompt, max_tokens=2000)

    def _synthesize_findings(self, findings: str, query: str) -> str:
        """Synthesize findings from chunked analysis."""
        prompt = f"""Synthesize these findings into a comprehensive answer.

Findings:
{findings[:8000]}

Query: {query}

Provide a clear synthesis."""

        return self.llm.generate(prompt, max_tokens=2000)
