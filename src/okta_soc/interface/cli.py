import argparse
import asyncio
from datetime import datetime, timedelta, timezone  # ⟵ add timezone here

from rich import print

from okta_soc.ingest.pipeline import fetch_and_process
from okta_soc.interface.show_all import run_show_all


def main() -> None:
    """
    Console entrypoint for the Okta Agentic SOC demo.

    Commands:
        okta-soc --hours 24
        okta-soc show-all
    """
    parser = argparse.ArgumentParser(
        description="Okta Agentic SOC pipeline runner."
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=None,
        help="Ingest Okta logs from the last N hours and run full pipeline.",
    )
    parser.add_argument(
        "action",
        nargs="?",
        default=None,
        help="Optional action: show-all",
    )

    args = parser.parse_args()

    # Pretty printer mode
    if args.action == "show-all":
        run_show_all()
        return

    # Pipeline run mode
    if args.hours is not None:
        # ✅ Use timezone-aware UTC datetime
        since = datetime.now(timezone.utc) - timedelta(hours=args.hours)
        asyncio.run(fetch_and_process(since))
        print(f"[green]Done processing Okta events from last {args.hours} hour(s).[/green]")
        return

    parser.print_help()


if __name__ == "__main__":
    main()
