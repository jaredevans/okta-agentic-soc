import json
from pathlib import Path
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table

DATA_DIR = Path("data")

console = Console()


def load_jsonl(path: Path):
    """Load a .jsonl file into a list of dicts. Return empty list if missing."""
    if not path.exists():
        return []
    items = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
    return items


def show_section(title: str, items: list):
    """Pretty-print a section with a title."""
    if not items:
        console.print(Panel(f"[yellow]No {title.lower()} found[/yellow]", title=title))
        return

    console.print(f"\n[bold underline]{title}[/bold underline]")
    for i, item in enumerate(items, start=1):
        console.print(
            Panel(
                Pretty(item, indent_guides=True),
                title=f"{title[:-1]} #{i}",
                expand=False,
                border_style="cyan",
            )
        )


def run_show_all():
    """Main entry for pretty-printing all .jsonl artifacts."""
    console.print("[bold green]=== Okta Agentic SOC Output ===[/bold green]\n")

    findings = load_jsonl(DATA_DIR / "findings.jsonl")
    incidents = load_jsonl(DATA_DIR / "incidents.jsonl")
    plans = load_jsonl(DATA_DIR / "plans.jsonl")
    commands = load_jsonl(DATA_DIR / "commands.jsonl")

    show_section("Findings", findings)
    show_section("Incidents", incidents)
    show_section("Plans", plans)
    show_section("Commands", commands)

    console.print("\n[green]Done displaying all output.[/green]")
