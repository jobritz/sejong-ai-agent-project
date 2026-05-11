"""
agent/executor.py — moves files, writes log entries, and manages the undo stack.

Design decisions:
- All moves are logged to a JSON-lines file BEFORE the move happens.
  If the process crashes mid-move, the log still has the intent.
- The undo stack is kept in memory. On restart you lose undo history,
  but the JSON log lets you reconstruct moves manually.
- Folder creation is idempotent (exist_ok=True).
"""

from __future__ import annotations
import json
import shutil
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path

from rich.console import Console

from config import CATEGORY_FOLDERS, MAX_UNDO_STACK
from agent.classifier import ClassifyResult

console = Console()


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------
@dataclass
class MoveRecord:
    timestamp: float
    filename: str
    source: str  # absolute path before move
    destination:str  # absolute path after move
    category: str
    confidence: float
    reason: str
    used_llm: bool


# ---------------------------------------------------------------------------
# Executor
# ---------------------------------------------------------------------------
class FileExecutor:
    """
    Moves files to their category folder and manages an undo stack.
    """

    def __init__(self, watch_dir: Path, log_path: Path):
        self.watch_dir = watch_dir
        self.log_path = log_path
        self.undo_stack: deque[MoveRecord] = deque(maxlen=MAX_UNDO_STACK)
        self._ensure_log_file()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def execute(self, filepath: Path, result: ClassifyResult) -> MoveRecord | None:
        """
        Move *filepath* to the appropriate category sub-folder.
        Returns the MoveRecord, or None if the file no longer exists.
        """
        if not filepath.exists():
            console.print(f"  [dim]File gone before move: {filepath.name}[/dim]")
            return None

        dest_folder = self._category_folder(result.category)
        dest_path = self._resolve_collision(dest_folder / filepath.name)

        record = MoveRecord(
            timestamp=time.time(),
            filename=filepath.name,
            source=str(filepath),
            destination=str(dest_path),
            category=result.category,
            confidence=result.confidence,
            reason=result.reason,
            used_llm=result.used_llm,
        )

        # Log intent first, then move (crash-safe ordering)
        self._write_log(record)
        shutil.move(str(filepath), str(dest_path))
        self.undo_stack.append(record)

        return record

    def undo_last(self) -> MoveRecord | None:
        """Move the last file back to its original location."""
        if not self.undo_stack:
            console.print("  [yellow]Nothing to undo.[/yellow]")
            return None

        record = self.undo_stack.pop()
        src = Path(record.destination)
        dest = Path(record.source)

        if not src.exists():
            console.print(
                f"  [red]Cannot undo: '{src.name}' not found at expected location.[/red]"
            )
            return None

        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dest))
        console.print(
            f"  [green]↩ Undone:[/green] '{record.filename}' "
            f"→ {dest.parent.name}/"
        )
        return record

    def undo_all(self) -> int:
        """Roll back all moves in the undo stack. Returns count undone."""
        count = 0
        while self.undo_stack:
            if self.undo_last():
                count += 1
        return count

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _category_folder(self, category: str) -> Path:
        folder_name = CATEGORY_FOLDERS.get(category, CATEGORY_FOLDERS["misc"])
        folder = self.watch_dir / folder_name
        folder.mkdir(exist_ok=True)
        return folder

    @staticmethod
    def _resolve_collision(path: Path) -> Path:
        """If path already exists, append _1, _2, … before the extension."""
        if not path.exists():
            return path
        stem, suffix = path.stem, path.suffix
        counter = 1
        while True:
            candidate = path.parent / f"{stem}_{counter}{suffix}"
            if not candidate.exists():
                return candidate
            counter += 1

    def _ensure_log_file(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_path.exists():
            self.log_path.write_text("")  # create empty file

    def _write_log(self, record: MoveRecord) -> None:
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(record)) + "\n")
