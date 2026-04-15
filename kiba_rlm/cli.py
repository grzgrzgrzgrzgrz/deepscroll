"""
kiba-rlm CLI - Command line interface for recursive document analysis.

Usage:
    kiba-rlm analyze ./docs --query "What are the main themes?"
    kiba-rlm analyze ./codebase --query "How does auth work?" --llm openai
    kiba-rlm research "DSGVO compliance" --sources urls.txt
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .core import RecursiveContextManager
from .llm import LLMInterface
from .navigator import DocumentNavigator

console = Console()


def load_files(path: str) -> list[str]:
    """Load files from a path (file or directory)."""
    p = Path(path)

    if not p.exists():
        raise click.ClickException(f"Path does not exist: {path}")

    if p.is_file():
        return [p.read_text(encoding="utf-8", errors="replace")]

    # Directory: load all text files
    files = []
    extensions = {".txt", ".md", ".py", ".js", ".ts", ".json", ".yaml", ".yml", ".toml", ".rst"}

    for file in p.rglob("*"):
        if file.is_file() and file.suffix.lower() in extensions:
            try:
                content = file.read_text(encoding="utf-8", errors="replace")
                files.append(f"# File: {file.relative_to(p)}\n\n{content}")
            except Exception as e:
                console.print(f"[yellow]Warning: Could not read {file}: {e}[/yellow]")

    if not files:
        raise click.ClickException(f"No supported files found in: {path}")

    return files


@click.group()
@click.version_option(version="0.1.0")
def cli() -> None:
    """
    kiba-rlm: Recursive Language Models for infinite context analysis.

    Analyze large document sets (10M+ tokens) using LLM-guided navigation.
    """
    pass


@cli.command()
@click.argument("path")
@click.option("-q", "--query", required=True, help="Analysis query")
@click.option(
    "--llm",
    default="claude",
    type=click.Choice(["claude", "openai"]),
    help="LLM provider to use",
)
@click.option("--model", default=None, help="Specific model to use")
@click.option("-o", "--output", default=None, help="Output file (default: stdout)")
@click.option("--format", "fmt", default="text", type=click.Choice(["text", "json", "markdown"]))
@click.option("--max-recursion", default=10, help="Maximum recursion depth")
@click.option("-v", "--verbose", is_flag=True, help="Verbose output")
def analyze(
    path: str,
    query: str,
    llm: str,
    model: Optional[str],
    output: Optional[str],
    fmt: str,
    max_recursion: int,
    verbose: bool,
) -> None:
    """
    Analyze documents or a codebase with recursive LLM navigation.

    PATH can be a file or directory. For directories, all supported text files
    are loaded and analyzed together.

    Examples:
        kiba-rlm analyze ./docs -q "Summarize the main concepts"
        kiba-rlm analyze ./src -q "How does authentication work?"
        kiba-rlm analyze report.pdf -q "What are the key findings?"
    """
    console.print(f"[bold]kiba-rlm[/bold] - Analyzing: {path}")
    console.print(f"Query: {query}\n")

    # Load files
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Loading files...", total=None)
        documents = load_files(path)

    total_chars = sum(len(d) for d in documents)
    console.print(f"Loaded {len(documents)} file(s), {total_chars:,} characters\n")

    # Initialize manager
    try:
        llm_interface = LLMInterface(provider=llm, model=model)
        manager = RecursiveContextManager(
            llm=llm_interface,
            max_recursion=max_recursion,
        )
    except ValueError as e:
        raise click.ClickException(str(e))

    # Run analysis
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Analyzing with recursive navigation...", total=None)
        result = manager.analyze(documents, query)

    # Output result
    if fmt == "json":
        output_data = json.dumps(
            {
                "query": query,
                "path": path,
                "files_analyzed": len(documents),
                "total_chars": total_chars,
                "result": result,
            },
            indent=2,
        )
        if output:
            Path(output).write_text(output_data)
            console.print(f"[green]Result saved to {output}[/green]")
        else:
            print(output_data)

    elif fmt == "markdown":
        md_content = f"""# Analysis Result

## Query
{query}

## Path
{path} ({len(documents)} files, {total_chars:,} characters)

## Result
{result}
"""
        if output:
            Path(output).write_text(md_content)
            console.print(f"[green]Result saved to {output}[/green]")
        else:
            console.print(Markdown(md_content))

    else:  # text
        console.print(Panel(result, title="[bold green]Analysis Result[/bold green]"))
        if output:
            Path(output).write_text(result)
            console.print(f"\n[green]Result saved to {output}[/green]")


@cli.command()
@click.argument("topic")
@click.option("--sources", default=None, help="File with URLs (one per line)")
@click.option(
    "--llm",
    default="claude",
    type=click.Choice(["claude", "openai"]),
    help="LLM provider",
)
@click.option("-o", "--output", default=None, help="Output file")
def research(
    topic: str,
    sources: Optional[str],
    llm: str,
    output: Optional[str],
) -> None:
    """
    Deep research on a topic using multiple sources.

    Examples:
        kiba-rlm research "DSGVO compliance for SaaS"
        kiba-rlm research "React performance" --sources urls.txt
    """
    console.print(f"[bold]kiba-rlm Research[/bold]")
    console.print(f"Topic: {topic}\n")

    documents: list[str] = []

    # Load sources if provided
    if sources:
        source_file = Path(sources)
        if source_file.exists():
            urls = [line.strip() for line in source_file.read_text().split("\n") if line.strip()]
            console.print(f"Found {len(urls)} source URLs")

            # Note: Web fetching would require additional dependencies
            console.print("[yellow]Note: Web fetching not yet implemented. Using topic query only.[/yellow]")
        else:
            raise click.ClickException(f"Sources file not found: {sources}")

    # For now, do a direct query (web research would require aiohttp)
    llm_interface = LLMInterface(provider=llm)

    prompt = f"""You are a research assistant. Provide a comprehensive analysis on the following topic.

Topic: {topic}

Please cover:
1. Key concepts and definitions
2. Current best practices
3. Common challenges and solutions
4. Relevant regulations or standards (if applicable)
5. Recommended resources for further reading

Provide well-structured, accurate information."""

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        progress.add_task("Researching...", total=None)
        result = llm_interface.generate(prompt, max_tokens=3000)

    console.print(Panel(result, title=f"[bold green]Research: {topic}[/bold green]"))

    if output:
        Path(output).write_text(result)
        console.print(f"\n[green]Result saved to {output}[/green]")


@cli.command()
@click.argument("path")
@click.option("-p", "--pattern", required=True, help="Search pattern (regex)")
@click.option("-i", "--ignore-case", is_flag=True, help="Case-insensitive search")
@click.option("-c", "--context", default=3, help="Lines of context")
def search(
    path: str,
    pattern: str,
    ignore_case: bool,
    context: int,
) -> None:
    """
    Search documents for a pattern.

    Examples:
        kiba-rlm search ./docs -p "authentication"
        kiba-rlm search ./src -p "TODO|FIXME" -i
    """
    documents = load_files(path)
    nav = DocumentNavigator(context_lines=context)

    matches = nav.grep(documents, pattern, ignore_case=ignore_case)

    if not matches:
        console.print("[yellow]No matches found.[/yellow]")
        return

    console.print(f"Found {len(matches)} matches:\n")

    for match in matches:
        console.print(f"[bold]Doc {match.doc_index}, Line {match.line_number}:[/bold]")

        # Context before
        for line in match.context_before:
            console.print(f"  [dim]{line}[/dim]")

        # Matching line with highlight
        console.print(f"  [yellow]{match.line_content}[/yellow]")

        # Context after
        for line in match.context_after:
            console.print(f"  [dim]{line}[/dim]")

        console.print()


@cli.command()
@click.argument("path")
def stats(path: str) -> None:
    """
    Show statistics about documents.

    Examples:
        kiba-rlm stats ./docs
        kiba-rlm stats ./src
    """
    documents = load_files(path)
    nav = DocumentNavigator()

    total_chars = sum(len(d) for d in documents)
    total_lines = sum(d.count("\n") + 1 for d in documents)
    total_words = sum(len(d.split()) for d in documents)

    console.print("[bold]Document Statistics[/bold]\n")
    console.print(f"Files: {len(documents)}")
    console.print(f"Total characters: {total_chars:,}")
    console.print(f"Total lines: {total_lines:,}")
    console.print(f"Total words: {total_words:,}")
    console.print(f"Estimated tokens: {total_chars // 4:,}")

    # File breakdown
    console.print("\n[bold]File Breakdown:[/bold]")
    for i, doc in enumerate(documents):
        first_line = doc.split("\n")[0][:60]
        console.print(f"  [{i}] {len(doc):,} chars - {first_line}...")


if __name__ == "__main__":
    cli()
