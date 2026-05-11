"""
utils/reporter.py — reads the JSON-lines log and prints a rich daily summary.

Run standalone:   python -m utils.reporter --log organizer.log
Or called by the scheduler inside main.py.
"""

from __future__ import annotations
import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


def load_log(log_path: Path, since_hours: int=24) -> list[dict]:
    """Load log entries from the last *since_hours* hours."""
    if not log_path.exists():
        return []

    cutoff = datetime.now().timestamp() - (since_hours * 3600)
    records = []

    with log_path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
                if rec.get("timestamp", 0) >= cutoff:
                    records.append(rec)
            except json.JSONDecodeError:
                continue  # skip malformed lines

    return records


def print_summary(log_path: Path, since_hours: int=24) -> None:
    """Print a rich summary table for the last N hours."""
    records = load_log(log_path, since_hours)

    console.rule(f"[bold]Daily Summary[/bold] — last {since_hours}h")

    if not records:
        console.print("  No files organised yet.")
        return

    # --- stats ---
    total = len(records)
    llm_calls = sum(1 for r in records if r.get("used_llm"))
    categories = Counter(r["category"] for r in records)
    by_hour = defaultdict(int)

    for r in records:
        dt = datetime.fromtimestamp(r["timestamp"])
        by_hour[dt.strftime("%H:00")] += 1

    avg_conf = sum(r.get("confidence", 0) for r in records) / total

    # --- overview table ---
    console.print(
        f"  Files moved: [bold]{total}[/bold]  |  "
        f"LLM calls: [cyan]{llm_calls}[/cyan]  |  "
        f"Avg confidence: [green]{avg_conf:.0%}[/green]"
    )

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold")
    table.add_column("Category", style="green")
    table.add_column("Count", justify="right")
    table.add_column("% of total", justify="right")

    for cat, count in categories.most_common():
        table.add_row(cat, str(count), f"{count/total:.0%}")

    console.print(table)

    # --- recent moves ---
    console.print("\n[bold]Last 5 moves:[/bold]")
    for r in records[-5:]:
        ts = datetime.fromtimestamp(r["timestamp"]).strftime("%H:%M:%S")
        src = Path(r["destination"]).name
        console.print(
            f"  [dim]{ts}[/dim]  {src}  →  "
            f"[green]{r['category']}[/green]  "
            f"[dim]({r['confidence']:.0%})[/dim]"
        )

    console.rule()


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Print organizer daily summary")
    parser.add_argument("--log", default="organizer.log", help="Path to log file")
    parser.add_argument("--hours", type=int, default=24, help="Hours to look back")
    args = parser.parse_args()

    print_summary(Path(args.log), since_hours=args.hours)
