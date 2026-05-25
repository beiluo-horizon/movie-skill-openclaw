"""CLI entry point for movie-crawl.

Per D-03: Single `search` subcommand for querying magnet links.
Per D-04: Supports both structured params (--show --season --episode)
          and natural language query string, auto-detecting format.

Usage:
    movie-crawl search "权力的游戏第三季第五集"
    movie-crawl search --show "权力的游戏" --season 3 --episode 5 --json
    movie-crawl search --show "Game of Thrones" -S 3 -E 5

The `configure` subcommand launches the interactive site config wizard.
"""

import asyncio
import sys
from typing import Optional

import typer
from rich.console import Console

from movie_skill.engine import CrawlerEngine
from movie_skill.parsers.episode import detect_input_mode, ParsedQuery
from movie_skill.output.json_writer import write_search_result, clean_magnet_dir
from movie_skill.output.terminal import (
    print_search_result,
    print_error,
    print_info,
)
from movie_skill.config.loader import ConfigError

app = typer.Typer(
    name="movie-crawl",
    help="Search Chinese media sites for magnet links",
    no_args_is_help=True,
)
console = Console()


@app.command()
def search(
    query: str = typer.Argument(
        "",
        help="Show name or natural language query (e.g. '权力的游戏第三季第五集')",
    ),
    show: Optional[str] = typer.Option(
        None, "--show", "-s",
        help="Show name (structured mode, use with --season/--episode)",
    ),
    season: Optional[int] = typer.Option(
        None, "--season", "-S",
        help="Season number",
    ),
    episode: Optional[int] = typer.Option(
        None, "--episode", "-E",
        help="Episode number",
    ),
    json_output: bool = typer.Option(
        False, "--json",
        help="Output as JSON instead of human-readable table",
    ),
    sites: Optional[str] = typer.Option(
        None, "--sites",
        help="Comma-separated list of site names to search (default: all configured)",
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", "-o",
        help="Directory for magnet output files (default: .magnet/)",
    ),
):
    """Search Chinese media sites for magnet links.

    If --show is provided, uses structured mode (--season, --episode optional).
    If only <query> argument is provided, auto-detects the format:
    - "权力的游戏第三季第五集" → show="权力的游戏", season=3, episode=5
    - "westworld s03e05" → show="westworld", season=3, episode=5
    - "权力的游戏" → show="权力的游戏" (no episode filter)
    """
    # Detect input mode per D-04
    if show:
        # Structured mode
        parsed = ParsedQuery(show=show, season=season, episode=episode)
    elif query:
        # NL mode: auto-detect
        parsed = detect_input_mode(query)
    else:
        print_error("Provide a show name or query string")
        print_info("Usage: movie-crawl search '权力的游戏第三季第五集'")
        print_info("   or: movie-crawl search --show '权力的游戏' --season 3 --episode 5")
        raise typer.Exit(code=1)

    if not parsed.show.strip():
        print_error("Could not parse a show name from your input")
        raise typer.Exit(code=1)

    # Build engine and run search
    try:
        clean_magnet_dir(output_dir)
        engine = CrawlerEngine()
        result = asyncio.run(
            engine.search(parsed.show, parsed.season, parsed.episode)
        )
    except ConfigError as e:
        print_error(f"Configuration error: {e}")
        print_info("Run 'movie-crawl configure' to set up your sites")
        raise typer.Exit(code=1)
    except Exception as e:
        print_error(f"Search failed: {e}")
        raise typer.Exit(code=1)

    # Handle all-sites-failed per D-07
    if result.total == 0:
        _handle_no_results(result, parsed)
        raise typer.Exit(code=1)

    # Write per-magnet JSON files
    try:
        files_written = write_search_result(result, output_dir=output_dir or ".magnet")
    except OSError as e:
        print_error(f"Failed to write output files: {e}")
        raise typer.Exit(code=1)

    # Output results
    if json_output:
        console.print(result.model_dump_json(indent=2, exclude_none=True))
    else:
        print_search_result(result)

    # Report file count
    if not json_output:
        print_info(f"Wrote {files_written} results to .magnet/{parsed.show}.json")


def _handle_no_results(result, parsed: ParsedQuery) -> None:
    """Handle the case when all sites returned no results (D-07)."""
    print_error("No results found from any source site")
    if result.errors:
        console.print("\nTried the following sites:")
        for error in result.errors:
            console.print(f"  [dim]- {error}[/]")
    else:
        print_info("No sites were configured. Run 'movie-crawl configure' to add sites.")
    print_info(f"Query: '{parsed.show}'")


@app.command()
def configure(
    sites_path: Optional[str] = typer.Option(
        None, "--sites-path",
        help="Path to sites.yaml (default: ~/.movie_skill/sites.yaml)",
    ),
):
    """Interactively create or edit site configuration.

    Launches a guided wizard to help users who don't know
    CSS/XPath selectors create a working sites.yaml file.
    """
    try:
        from movie_skill.wizard.configure import run_wizard
        run_wizard(sites_path=sites_path or "~/.movie_skill/sites.yaml")
    except ImportError as e:
        print_error(f"Wizard dependencies not installed: {e}")
        print_info("Install with: pip install movie-skill[wizard]")
        raise typer.Exit(code=1)
    except Exception as e:
        print_error(f"Configuration failed: {e}")
        raise typer.Exit(code=1)


def main():
    """Entry point for movie-crawl CLI."""
    app()
