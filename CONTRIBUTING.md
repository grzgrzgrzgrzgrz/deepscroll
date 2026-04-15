# Contributing

## Development Setup

```bash
git clone https://github.com/grzgrzgrzgrzgrz/deepscroll
cd deepscroll
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev,mcp]'
```

Copy [`.env.example`](./.env.example) if you want local defaults for provider keys
or MCP runtime settings.

## Checks

Run these before opening or updating a pull request:

```bash
pytest
ruff check .
mypy deepscroll
python -m build
```

## Pull Requests

- keep changes focused and intentional
- update documentation when behavior or setup changes
- include tests for behavioral changes where practical
- prefer small PRs over broad refactors

## Security

For security-sensitive issues, follow [`SECURITY.md`](./SECURITY.md) instead of
opening a public issue.
