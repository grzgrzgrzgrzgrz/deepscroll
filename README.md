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

Install the MCP server extras when you want Claude Code integration:

```bash
pip install 'deepscroll[mcp]'
```

Or install from source:

```bash
git clone https://github.com/grzgrzgrzgrzgrz/deepscroll
cd deepscroll
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,mcp]'
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

Add an MCP server entry to your Claude Code MCP configuration:

```json
{
  "mcpServers": {
    "deepscroll": {
      "command": "python",
      "args": ["-m", "deepscroll.mcp_server"],
      "env": {
        "OPENAI_API_KEY": "${OPENAI_API_KEY}",
        "RLM_LLM_PROVIDER": "openai",
        "RLM_LLM_MODEL": "gpt-5.4-mini",
        "RLM_MAX_TOKENS": "4096",
        "RLM_TEMPERATURE": "0.2"
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
# For OpenAI
export OPENAI_API_KEY=sk-...

# For Claude (Anthropic)
export ANTHROPIC_API_KEY=sk-ant-...

# Optional MCP / runtime overrides
export RLM_LLM_PROVIDER=openai
export RLM_LLM_MODEL=gpt-5.4-mini
export RLM_MAX_TOKENS=4096
export RLM_TEMPERATURE=0.2
```

A sample file is available in [`.env.example`](./.env.example).

### Supported File Types

The CLI and MCP server automatically process text-based files such as:
- Code: `.py`, `.js`, `.ts`, `.tsx`, `.jsx`, `.go`, `.rs`, `.java`, `.c`, `.cpp`, `.h`
- Docs: `.md`, `.txt`, `.rst`, `.html`
- Config: `.json`, `.yaml`, `.yml`, `.toml`
- Shell: `.sh`, `.bash`, `.zsh`
- SQL: `.sql`

Binary formats such as PDFs are not parsed directly. Convert them to text or
Markdown first if you want reliable analysis.

## Security

LLM-generated code runs in a **RestrictedPython-based, best-effort sandbox** that:
- blocks direct access to dangerous built-ins such as `open`, `eval`, `exec`, and `__import__`
- exposes only a narrow set of safe helpers for navigation and analysis
- provides Python-level restrictions, not full OS- or container-level isolation

If you analyze untrusted content, run `deepscroll` inside an isolated environment
such as a dedicated virtual machine or container. See [`SECURITY.md`](./SECURITY.md)
for reporting guidance and threat-model notes.

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
    documents=["contract_v1.md", "contract_v2.md"],
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
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,mcp]'

# Run tests
pytest

# Format code
black deepscroll tests examples
ruff check .

# Type check
mypy deepscroll

# Build release artifacts
python -m build
```

## Community

- [Contributing guide](./CONTRIBUTING.md)
- [Code of conduct](./CODE_OF_CONDUCT.md)
- [Security policy](./SECURITY.md)
- [Issue tracker](https://github.com/grzgrzgrzgrzgrz/deepscroll/issues)

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
