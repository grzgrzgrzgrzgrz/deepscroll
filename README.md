# deepscroll

**Recursive Language Models for Infinite Context Analysis**

Analyze documents of any size (10M+ tokens) using LLM-guided recursive navigation.

> ## 📄 Research Foundation
>
> This project is an **independent open-source implementation** of the technique introduced in:
>
> **Zhang, A. L., Kraska, T., & Khattab, O. (2026).** *Recursive Language Models.*
> arXiv preprint [arXiv:2512.24601](https://arxiv.org/abs/2512.24601).
> DOI: [10.48550/arXiv.2512.24601](https://doi.org/10.48550/arXiv.2512.24601)
>
> All credit for the underlying method belongs to the original authors at MIT.
> `deepscroll` is not affiliated with or endorsed by the paper's authors or MIT.
> See the [Citation](#citation) section below for BibTeX.

## Installation

```bash
pip install deepscroll
```

Or install from source:

```bash
git clone https://github.com/grzgrzgrzgrzgrz/deepscroll
cd deepscroll
pip install -e .
```

## Quick Start

### Python API

```python
from deepscroll import analyze_large_context

# Analyze any number of documents
result = analyze_large_context(
    documents=["doc1.txt", "doc2.txt", "./my-codebase/"],
    query="What are the main architectural patterns used?"
)
print(result)
```

### CLI

```bash
# Analyze a codebase
deepscroll analyze ./src --query "How does authentication work?"

# Analyze documents
deepscroll analyze ./docs --query "Summarize the key findings"

# Search with context
deepscroll search ./src --pattern "TODO|FIXME"

# Get statistics
deepscroll stats ./my-project
```

### Claude Code MCP Integration

Add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "deepscroll": {
      "command": "python",
      "args": ["-m", "deepscroll.mcp_server"],
      "env": {
        "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}"
      }
    }
  }
}
```

Then in Claude Code, you can use:

```
Use the analyze_codebase tool to understand how the auth system works in ./src
```

## How It Works

Traditional LLMs have context window limits (typically 128K-200K tokens). deepscroll breaks this barrier using the **Recursive Language Model** technique:

1. **Documents as Variables**: Instead of putting all documents in the context, they're stored as external variables
2. **LLM-Generated Navigation**: The LLM writes Python code to search and navigate through documents
3. **Secure Execution**: Code runs in a RestrictedPython sandbox for safety
4. **Recursive Drilling**: For complex queries, the system recursively analyzes subsets

```
┌─────────────────────────────────────────────────┐
│                    Query                         │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│          RecursiveContextManager                 │
│  ┌───────────────────────────────────────────┐  │
│  │ 1. Load documents as external variables    │  │
│  │ 2. LLM generates navigation code          │  │
│  │ 3. Execute in secure sandbox              │  │
│  │ 4. If needed, recurse on subset           │  │
│  │ 5. Synthesize final answer                │  │
│  └───────────────────────────────────────────┘  │
└─────────────────────┬───────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────┐
│                   Answer                         │
└─────────────────────────────────────────────────┘
```

## API Reference

### RecursiveContextManager

The main class for document analysis.

```python
from deepscroll import RecursiveContextManager

manager = RecursiveContextManager(
    llm="claude",           # or "openai"
    max_recursion=10,       # maximum recursive depth
    chunk_size=4000,        # characters per chunk
    overlap=200             # overlap between chunks
)

result = manager.analyze(
    documents=["doc1.txt", "doc2.txt"],
    query="What are the key themes?"
)
```

### DocumentNavigator

Tools for searching and navigating documents.

```python
from deepscroll import DocumentNavigator

nav = DocumentNavigator()

# Search with regex
matches = nav.grep(documents, r"authentication|auth")

# Get sections around matches
sections = nav.grep_sections(documents, r"TODO", section_size=500)

# Chunk a large document
chunks = nav.chunk(large_document)

# Get document summary (head + tail)
summary = nav.summarize(document, head_lines=20, tail_lines=20)
```

### LLMInterface

Unified interface for LLM providers.

```python
from deepscroll import LLMInterface

llm = LLMInterface(
    provider="claude",      # or "openai"
    model="claude-sonnet-4-20250514",
    fallback_provider="openai"  # optional fallback
)

response = llm.generate(
    prompt="Explain this code",
    system="You are a code reviewer",
    max_tokens=1000
)
```

## Configuration

### Environment Variables

```bash
# For Claude (Anthropic)
export ANTHROPIC_API_KEY=sk-ant-...

# For OpenAI
export OPENAI_API_KEY=sk-...
```

### Supported File Types

The CLI and MCP server automatically process these file types:
- Code: `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.go`, `.rs`, `.java`, `.c`, `.cpp`, `.h`
- Docs: `.md`, `.txt`, `.rst`, `.html`
- Config: `.json`, `.yaml`, `.yml`, `.toml`
- Shell: `.sh`, `.bash`, `.zsh`
- SQL: `.sql`

## Security

LLM-generated code runs in a **RestrictedPython sandbox** that:
- Blocks file system access
- Blocks network access
- Blocks code execution (`eval`, `exec`, `__import__`)
- Allows only safe built-in functions
- Provides safe versions of `re`, `json`, `math`, `collections`

## Examples

### Analyze a Monorepo

```python
from deepscroll import analyze_large_context

# Works with codebases of any size
result = analyze_large_context(
    documents=["./packages/"],
    query="How are the packages related to each other?"
)
```

### Compare Documents

```python
from deepscroll import RecursiveContextManager

manager = RecursiveContextManager()

result = manager.analyze(
    documents=["contract_v1.pdf", "contract_v2.pdf"],
    query="What are the key differences between these versions?"
)
```

### Code Review

```bash
deepscroll analyze ./src \
    --query "Find potential security issues" \
    --output security-review.md \
    --format markdown
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
black deepscroll
ruff check deepscroll

# Type check
mypy deepscroll
```

## License

MIT

## Citation

If you use `deepscroll` in your research or work, **please cite the original paper** this
implementation is based on:

**Plain text:**

> Zhang, A. L., Kraska, T., & Khattab, O. (2026). *Recursive Language Models.*
> arXiv preprint arXiv:2512.24601. https://doi.org/10.48550/arXiv.2512.24601

**BibTeX:**

```bibtex
@article{zhang2026recursive,
  title   = {Recursive Language Models},
  author  = {Zhang, Alex L. and Kraska, Tim and Khattab, Omar},
  journal = {arXiv preprint arXiv:2512.24601},
  year    = {2026},
  month   = jan,
  doi     = {10.48550/arXiv.2512.24601},
  url     = {https://arxiv.org/abs/2512.24601},
  note    = {v1 submitted December 31, 2025; v2 revised January 28, 2026}
}
```

## Credits

Additional techniques and inspiration:

- [StreamingLLM](https://github.com/mit-han-lab/streaming-llm) — attention sink techniques

## Disclaimer

`deepscroll` is an **independent open-source implementation** and is **not affiliated with,
endorsed by, or sponsored by** the authors of the Recursive Language Models paper, MIT,
or any of their affiliated institutions. Any errors in this implementation are our own.

Built by **Grzegorz Olszówka** — [grzgrzgrz.com](https://grzgrzgrz.com) · [kiba.berlin](https://kiba.berlin)
