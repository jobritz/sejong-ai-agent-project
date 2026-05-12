"""
main.py — entry point for the Smart File Organizer Agent.

Usage:
  python main.py --watch ~/Downloads          # watch a folder
  python main.py --watch ~/Downloads --undo   # undo last move
  python main.py --watch ~/Downloads --undo-all  # undo everything
  python main.py --summary                    # print today's summary
"""

from __future__ import annotations
import argparse
import os
import signal
import sys
import time
from pathlib import Path

import schedule
from dotenv import load_dotenv
from rich.console import Console
from watchdog.observers import Observer

from agent.classifier import FileClassifier
from agent.executor import FileExecutor
from agent.watcher import OrganizerEventHandler
from config import SUMMARY_HOUR
from utils.reporter import print_summary
from utils.ollama import ensure_ollama_ready, shutdown_ollama 
from config import WATCH_DIR, LOG_DIR

load_dotenv()
console = Console()

LOG_FILENAME = "organizer.log"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def build_agent(watch_dir: Path):
    """Instantiate and wire up all agent components."""
    log_path = LOG_DIR / LOG_FILENAME
    classifier = FileClassifier()
    executor = FileExecutor(watch_dir, log_path)
    handler = OrganizerEventHandler(classifier, executor)
    return classifier, executor, handler, log_path


def start_watching(watch_dir: Path) -> None:
    """Main watch loop — blocks until Ctrl+C."""
    watch_dir = watch_dir.expanduser().resolve()
    if not watch_dir.exists():
        console.print(f"[red]Error:[/red] '{watch_dir}' does not exist.")
        sys.exit(1)

    ensure_ollama_ready()
    classifier, executor, handler, log_path = build_agent(watch_dir)

    console.print(f"\n[bold green]Smart File Organizer Agent[/bold green]")
    console.print(f"  Watching: [cyan]{watch_dir}[/cyan]")
    console.print(f"  Model:    [cyan]{classifier.model}[/cyan]")
    console.print(f"  Log:      [cyan]{log_path}[/cyan]")
    console.print("  Press [bold]Ctrl+C[/bold] to stop.\n")

    observer = Observer()
    observer.schedule(handler, str(watch_dir), recursive=False)
    observer.start()

    def _shutdown(sig, frame):
        console.print("\n[yellow]Shutting down...[/yellow]")
        observer.stop()
        shutdown_ollama()
        print_summary(log_path, since_hours=24)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except Exception as e:
        console.print(f"[red]Unexpected error:[/red] {e}")
        observer.stop()
        raise
    finally:
        observer.join()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Smart File Organizer Agent — AI-powered file sorting"
    )
    parser.add_argument(
        "--watch", "-w",
        type=Path,
        default=Path(os.getenv("WATCH_DIR", str(WATCH_DIR))),
        help="Folder to watch (default: ~/Downloads or $WATCH_DIR)",
    )
    parser.add_argument(
        "--undo",
        action="store_true",
        help="Undo the last file move and exit",
    )
    parser.add_argument(
        "--undo-all",
        action="store_true",
        help="Undo ALL recorded moves and exit",
    )
    parser.add_argument(
        "--summary",
        action="store_true",
        help="Print today's summary and exit",
    )
    parser.add_argument(
        "--hours",
        type=int,
        default=24,
        help="Hours to look back for --summary (default: 24)",
    )
    args = parser.parse_args()

    watch_dir = args.watch.expanduser().resolve()

    if args.summary:
        print_summary(watch_dir / LOG_FILENAME, since_hours=args.hours)
        return

    if args.undo or args.undo_all:
        _, executor, _, _ = build_agent(watch_dir)
        # Rebuild undo stack from log (last N entries)
        # For a full implementation, load from log here.
        # For now we remind the user the stack is session-only.
        console.print(
            "[yellow]Note:[/yellow] The undo stack is session-only. "
            "Run the agent first, then undo within the same session.\n"
            "For persistent undo, see Week 3 of the implementation plan."
        )
        return

    start_watching(watch_dir)


if __name__ == "__main__":
    main()
