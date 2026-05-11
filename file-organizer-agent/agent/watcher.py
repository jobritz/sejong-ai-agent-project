"""
agent/watcher.py — watchdog event handler that feeds new files into the pipeline.

Why we use a short sleep before processing:
  Browsers and download managers write files in chunks. If we react to the
  first CREATE event, we might try to classify an empty or partial file.
  A small delay (MIN_FILE_AGE_SECONDS in config) lets the write finish.
"""

from __future__ import annotations
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler, FileCreatedEvent
from rich.console import Console

from config import MIN_FILE_AGE_SECONDS, CATEGORY_FOLDERS
from agent.classifier import FileClassifier
from agent.executor import FileExecutor

console = Console()

# Folder names we create — ignore events inside them to avoid infinite loops
MANAGED_FOLDER_NAMES = set(CATEGORY_FOLDERS.values())


class OrganizerEventHandler(FileSystemEventHandler):
    """
    Reacts to file creation events in the watched directory.
    Delegates classification to FileClassifier and action to FileExecutor.
    """

    def __init__(self, classifier: FileClassifier, executor: FileExecutor):
        super().__init__()
        self.classifier = classifier
        self.executor = executor
        self.files_processed = 0
        self.files_skipped = 0

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return

        filepath = Path(event.src_path)

        # Skip files inside managed sub-folders (we created those)
        if filepath.parent.name in MANAGED_FOLDER_NAMES:
            return

        # Skip hidden files and temp files (e.g. .DS_Store, .part, ~$...)
        if self._is_temp_file(filepath):
            self.files_skipped += 1
            return

        # Wait for the file to finish writing
        time.sleep(MIN_FILE_AGE_SECONDS)

        # File might have been moved/deleted while we waited
        if not filepath.exists():
            return

        self._process_file(filepath)

    # ------------------------------------------------------------------
    def _process_file(self, filepath: Path) -> None:
        console.print(f"\n[bold]New file:[/bold] {filepath.name}")

        # Classify
        result = self.classifier.classify(filepath)
        llm_tag = "[cyan](LLM)[/cyan]" if result.used_llm else "[dim](rule)[/dim]"
        console.print(
            f"  {llm_tag} → [green]{result.category}[/green] "
            f"({result.confidence:.0%}) — {result.reason}"
        )

        # Execute move
        record = self.executor.execute(filepath, result)
        if record:
            dest = Path(record.destination)
            console.print(f"  [dim]Moved → {dest.parent.name}/{dest.name}[/dim]")
            self.files_processed += 1

    # ------------------------------------------------------------------
    @staticmethod
    def _is_temp_file(path: Path) -> bool:
        name = path.name
        return (
            name.startswith(".")  # hidden files
            or name.startswith("~$")  # Office temp files
            or name.endswith(".part")  # Firefox partial downloads
            or name.endswith(".crdownload")  # Chrome partial downloads
            or name.endswith(".tmp")
        )
