# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line interface: parse, scan, apply, undo."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from . import apply as apply_module
from .config import Settings
from .models import Confidence, MediaKind
from .parse import parse_path
from .plan import Plan, PlanAction
from .providers import TmdbProvider
from .scanner import iter_videos, scan_library
from .serde import dump_plan, load_plan

app = typer.Typer(
    name="kemptd",
    help="Tidy, provider-backed media library organizer.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

_CONFIDENCE_STYLE = {
    Confidence.HIGH: "green",
    Confidence.MEDIUM: "yellow",
    Confidence.LOW: "red",
    Confidence.NONE: "dim",
}


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"kemptd {__version__}")
        raise typer.Exit


@app.callback()
def main(
    _version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """kemptd — scan, match, plan, and apply a tidy media library."""


@app.command()
def parse(
    path: Annotated[Path, typer.Argument(exists=True, help="File or directory to parse.")],
    kind: Annotated[
        MediaKind | None,
        typer.Option("--kind", "-k", help="Hint parsing toward movie or episode."),
    ] = None,
) -> None:
    """Parse media filenames under PATH and print what kemptd understood (no changes)."""
    videos = list(iter_videos(path))
    if not videos:
        console.print("[yellow]No video files found.[/]")
        raise typer.Exit(code=1)

    table = Table(title=f"Parsed {len(videos)} file(s)")
    table.add_column("Kind", style="cyan")
    table.add_column("Title")
    table.add_column("Year", justify="right")
    table.add_column("S/E", style="green")
    table.add_column("File", style="dim", overflow="fold")
    for video in videos:
        pm = parse_path(video, kind_hint=kind)
        if pm.is_absolute_numbered:
            se = "abs " + ",".join(str(e) for e in pm.absolute_episodes[:4])
        elif pm.season is not None:
            se = f"S{pm.season:02d}" + "".join(f"E{e:02d}" for e in pm.episodes)
        else:
            se = "-"
        table.add_row(pm.kind.value, pm.title or "[red]?[/]", str(pm.year or ""), se, video.name)
    console.print(table)


def _render_plan(plan: Plan) -> None:
    table = Table(title="Plan")
    table.add_column("Action", style="bold")
    table.add_column("Conf")
    table.add_column("Source → Destination", overflow="fold")
    for item in plan.items:
        style = _CONFIDENCE_STYLE[item.confidence]
        if item.action is PlanAction.MOVE and item.destination is not None:
            detail = f"{item.source.name}  →  {item.destination}"
            action = "[green]move[/]"
        else:
            detail = f"{item.source.name}  —  [dim]{item.reason}[/]"
            action = "[dim]skip[/]"
        table.add_row(action, f"[{style}]{item.confidence.value}[/]", detail)
    console.print(table)
    console.print(f"[green]{len(plan.moves)} move(s)[/], [dim]{len(plan.skips)} skip(s)[/]")


def _render_report(report: apply_module.ApplyReport) -> None:
    console.print(
        f"[green]moved {report.moved}[/] · [dim]skipped {report.skipped}[/] · "
        f"[red]failed {report.failed}[/]"
    )
    if report.journal_path is not None:
        console.print(
            f"[dim]Journal: {report.journal_path}  (undo: kemptd undo {report.journal_path})[/]"
        )


@app.command()
def scan(
    path: Annotated[
        Path,
        typer.Argument(exists=True, file_okay=False, help="Library directory to organize."),
    ],
    apply_: Annotated[
        bool, typer.Option("--apply", help="Execute the plan (default: dry-run).")
    ] = False,
    plan_out: Annotated[
        Path | None, typer.Option("--plan-out", help="Write the plan to this JSON file.")
    ] = None,
    limit: Annotated[
        int | None, typer.Option("--limit", help="Only process the first N files.")
    ] = None,
) -> None:
    """Scan PATH, match against TMDb, and build (and optionally apply) a plan."""
    settings = Settings.from_env()
    if not settings.tmdb_api_key:
        console.print("[red]Set KEMPTD_TMDB_API_KEY to enable matching.[/]")
        raise typer.Exit(code=2)

    with TmdbProvider(settings.tmdb_api_key) as provider:
        plan = scan_library(path, provider, limit=limit)

    _render_plan(plan)
    if plan_out is not None:
        dump_plan(plan, plan_out)
        console.print(f"[green]Plan written:[/] {plan_out}")

    if apply_:
        journal = (
            (plan_out.with_suffix(".journal.json")) if plan_out else path / ".kemptd-journal.json"
        )
        _render_report(apply_module.apply_plan(plan, journal_path=journal))
    else:
        console.print("[dim]Dry run — nothing moved. Re-run with --apply to execute.[/]")


@app.command()
def apply(
    plan_file: Annotated[
        Path, typer.Argument(exists=True, help="Plan JSON from `scan --plan-out`.")
    ],
    journal: Annotated[
        Path | None, typer.Option("--journal", help="Where to write the undo journal.")
    ] = None,
) -> None:
    """Execute a previously-saved plan."""
    plan = load_plan(plan_file)
    journal_path = journal or plan_file.with_suffix(".journal.json")
    _render_report(apply_module.apply_plan(plan, journal_path=journal_path))


@app.command()
def undo(
    journal_file: Annotated[Path, typer.Argument(exists=True, help="Journal written by `apply`.")],
) -> None:
    """Reverse the moves recorded in a journal."""
    restored = apply_module.undo(journal_file)
    console.print(f"[green]Restored {restored} file(s).[/]")


if __name__ == "__main__":  # pragma: no cover
    app()
