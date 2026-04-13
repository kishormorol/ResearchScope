"""ResearchScope CLI entry point."""

from __future__ import annotations

import typer
from rich.console import Console
from rich.table import Table

from researchscope.analysis import find_research_gaps, rank_papers
from researchscope.collectors import ArxivCollector, SemanticScholarCollector
from researchscope.storage import PaperStore

app = typer.Typer(
    name="researchscope",
    help="Open-source research intelligence for CS papers.",
    no_args_is_help=True,
)
console = Console()

_NO_PAPERS_MSG = (
    "[yellow]No papers saved yet. "
    "Run [bold]researchscope search --save[/bold] first.[/yellow]"
)


@app.command()
def search(
    query: str = typer.Argument(..., help="Search query (arXiv syntax supported)."),
    source: str = typer.Option(
        "arxiv", help="Data source: 'arxiv' or 'semantic_scholar'."
    ),
    limit: int = typer.Option(10, help="Maximum number of results."),
    save: bool = typer.Option(False, "--save", "-s", help="Persist results locally."),
) -> None:
    """Search for papers on arXiv or Semantic Scholar."""
    papers = []
    with console.status(f"Searching [bold]{source}[/bold] for '{query}'…"):
        if source == "arxiv":
            papers = ArxivCollector().search(query, max_results=limit)
        elif source == "semantic_scholar":
            with SemanticScholarCollector() as collector:
                papers = collector.search(query, limit=limit)
        else:
            console.print(
                f"[red]Unknown source '{source}'. "
                "Use 'arxiv' or 'semantic_scholar'.[/red]"
            )
            raise typer.Exit(code=1)

    ranked = rank_papers(papers)

    table = Table(title=f"Results for '{query}' ({source})", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", min_width=40)
    table.add_column("Authors")
    table.add_column("Date", width=12)
    table.add_column("Citations", justify="right", width=10)

    for idx, paper in enumerate(ranked, start=1):
        authors_str = ", ".join(paper.authors[:2])
        if len(paper.authors) > 2:
            authors_str += " et al."
        table.add_row(
            str(idx),
            paper.title,
            authors_str,
            str(paper.published) if paper.published else "—",
            str(paper.citation_count),
        )

    console.print(table)

    if save:
        with PaperStore() as store:
            for paper in ranked:
                store.upsert(paper)
        console.print(f"[green]Saved {len(ranked)} paper(s) to local store.[/green]")


@app.command()
def list_papers(
    limit: int | None = typer.Option(
        None, help="Limit the number of results shown."
    ),
) -> None:
    """List all locally saved papers."""
    with PaperStore() as store:
        papers = store.all()

    if not papers:
        console.print(_NO_PAPERS_MSG)
        return

    ranked = rank_papers(papers)
    if limit is not None:
        ranked = ranked[:limit]

    table = Table(title="Saved Papers", show_lines=True)
    table.add_column("#", style="dim", width=3)
    table.add_column("Title", min_width=40)
    table.add_column("Source", width=18)
    table.add_column("Date", width=12)
    table.add_column("Citations", justify="right", width=10)

    for idx, paper in enumerate(ranked, start=1):
        table.add_row(
            str(idx),
            paper.title,
            paper.source,
            str(paper.published) if paper.published else "—",
            str(paper.citation_count),
        )

    console.print(table)


@app.command()
def gaps(
    top_n: int = typer.Option(10, help="Number of gap topics to display."),
) -> None:
    """Identify research gaps from locally saved papers."""
    with PaperStore() as store:
        papers = store.all()

    if not papers:
        console.print(_NO_PAPERS_MSG)
        return

    gap_keywords = find_research_gaps(papers, top_n=top_n)

    if not gap_keywords:
        console.print("[yellow]Not enough keyword data to identify gaps.[/yellow]")
        return

    console.print("[bold]Potential research gaps (least-covered topics):[/bold]")
    for i, kw in enumerate(gap_keywords, start=1):
        console.print(f"  {i}. {kw}")


if __name__ == "__main__":
    app()
