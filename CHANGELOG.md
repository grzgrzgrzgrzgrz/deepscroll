# Changelog

All notable changes to `deepscroll` are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Unified default OpenAI model across library, MCP server, and examples to
  `gpt-4o-mini` (widely available baseline; override via `RLM_LLM_MODEL`).
- Fallback error message in `core.py` is now English (was German).
- README now surfaces alpha/experimental status prominently.

### Added
- `CHANGELOG.md`.
- Status, license, and Python-version badges in README.

## [0.1.0] — 2026-04-15

Initial public release.

### Added
- `RecursiveContextManager`: recursive navigation of arbitrarily large corpora
  using LLM-generated Python code.
- `SecurePythonREPL`: RestrictedPython sandbox for running LLM-authored
  navigation code safely (no filesystem, network, or arbitrary imports).
- `DocumentNavigator`: chunking, grep, grep-with-sections, head/tail summaries.
- `FileIndex`: lazy-loading index of large codebases with filename and content
  search.
- `LLMInterface`: unified wrapper for Anthropic and OpenAI providers with an
  optional fallback provider.
- CLI (`deepscroll`) with `analyze`, `search`, and `stats` subcommands.
- MCP server (`python -m deepscroll.mcp_server`) exposing `analyze_codebase`,
  `analyze_documents`, `deep_search`, and `document_stats` tools for Claude
  Code and other MCP clients.
- Examples: codebase analysis and deep research workflows.
- Tests for core, navigator, and REPL modules.
- GitHub Actions CI running tests, `ruff`, `mypy`, and a build check on
  Python 3.9 – 3.13.

[Unreleased]: https://github.com/grzgrzgrzgrzgrz/deepscroll/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/grzgrzgrzgrzgrz/deepscroll/releases/tag/v0.1.0
