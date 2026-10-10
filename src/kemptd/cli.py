# SPDX-License-Identifier: GPL-3.0-or-later
"""Command-line interface.

``parse`` is implemented today (it exercises the pure core end to end). ``scan``,
``apply`` and ``undo`` are declared so the command surface is stable while the
provider and apply layers land in subsequent changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from . import __version__
from .models import MediaKind
from .parse import parse_path

app = typer.Typer(
    name="kemptd",
    help="Tidy, provider-backed media library organizer.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()

_VIDEO_SUFFIXES = {".mkv", ".mp4", ".avi", ".m4v", ".mov", ".ts", ".wmv"}


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


def _iter_videos(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in _VIDEO_SUFFIXES else []
    return sorted(p for p in root.rglob("*") if p.is_file() and p.suffix.lower() in _VIDEO_SUFFIXES)


@app.command()
def parse(
    path: Annotated[Path, typer.Argument(exists=True, help="File or directory to parse.")],
    kind: Annotated[
        MediaKind | None,
        typer.Option("--kind", "-k", help="Hint parsing toward movie or episode."),
    ] = None,
) -> None:
    """Parse media filenames under PATH and print what kemptd understood.

    This runs the real parser; it does not touch the files or contact any
    provider. Use it to sanity-check how a messy library reads before planning.
    """
    videos = _iter_videos(path)
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
            eps = "".join(f"E{e:02d}" for e in pm.episodes)
            se = f"S{pm.season:02d}{eps}"
        else:
            se = "-"
        table.add_row(
            pm.kind.value,
            pm.title or "[red]?[/]",
            str(pm.year or ""),
            se,
            video.name,
        )

    console.print(table)


@app.command()
def scan() -> None:  # pragma: no cover - placeholder for the next change
    """Scan a library, match against providers, and emit a plan (coming soon)."""
    console.print("[yellow]`scan` lands in the next change — `parse` works today.[/]")
    raise typer.Exit(code=2)


if __name__ == "__main__":  # pragma: no cover
    app()
