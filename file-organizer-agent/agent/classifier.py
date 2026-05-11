"""
agent/classifier.py — content-aware classifier using a local Ollama LLM.

Pipeline:
  1. Extract a text snippet from the file (PDF, DOCX, TXT, …)
  2. Scan the Studium folder tree to get available semesters + lectures
  3. Ask Ollama to pick the best (semester, lecture) match
  4. Return a ClassifyResult with the target path
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

import ollama
import fitz          # pymupdf
import docx          # python-docx
from rich.console import Console

from config import (
    STUDIUM_DIR, OLLAMA_MODEL, OLLAMA_URL,
    MAX_CONTENT_CHARS, READABLE_EXTENSIONS, CONFIDENCE_THRESHOLD,
)

console = Console()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------
@dataclass
class ClassifyResult:
    semester:   str        # e.g. "1. Semester"
    lecture:    str        # e.g. "Mathematik 1"
    confidence: float
    reason:     str
    error:      str = ""

    @property
    def target_dir(self) -> Path:
        return STUDIUM_DIR / self.semester / self.lecture

    @property
    def is_confident(self) -> bool:
        return self.confidence >= CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# Folder scanner
# ---------------------------------------------------------------------------
def scan_studium_tree() -> dict[str, list[str]]:
    """
    Returns {semester_name: [lecture_name, …]} by reading the real folder tree.
    Example: {"1. Semester": ["Mathematik 1", "Informatik"], …}
    """
    tree: dict[str, list[str]] = {}
    if not STUDIUM_DIR.exists():
        raise FileNotFoundError(
            f"Studium folder not found: {STUDIUM_DIR}\n"
            "Create it first or update STUDIUM_DIR in config.py"
        )
    for sem_dir in sorted(STUDIUM_DIR.iterdir()):
        if sem_dir.is_dir() and not sem_dir.name.startswith("."):
            lectures = [
                d.name for d in sorted(sem_dir.iterdir())
                if d.is_dir() and not d.name.startswith(".")
            ]
            tree[sem_dir.name] = lectures
    return tree


# ---------------------------------------------------------------------------
# Content extractor
# ---------------------------------------------------------------------------
def extract_text(filepath: Path) -> str:
    """Extract a short text snippet from the file for LLM context."""
    ext = filepath.suffix.lower()
    text = ""

    try:
        if ext == ".pdf":
            doc = fitz.open(str(filepath))
            for page in doc:
                text += page.get_text()
                if len(text) >= MAX_CONTENT_CHARS:
                    break
            doc.close()

        elif ext in {".docx", ".doc"}:
            document = docx.Document(str(filepath))
            text = "\n".join(p.text for p in document.paragraphs)

        elif ext in READABLE_EXTENSIONS:
            text = filepath.read_text(encoding="utf-8", errors="ignore")

    except Exception as e:
        console.print(f"  [yellow]Content extract warning:[/yellow] {e}")

    return text[:MAX_CONTENT_CHARS].strip()


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------
class FileClassifier:
    def __init__(self):
        # Validate Ollama is reachable at startup
        try:
            client = ollama.Client(host=OLLAMA_URL)
            client.list()   # raises if Ollama isn't running
            self.client = client
            self.model = OLLAMA_MODEL
        except Exception:
            raise RuntimeError(
                "Cannot reach Ollama at " + OLLAMA_URL + "\n"
                "Start it with: ollama serve"
            )
        self.tree = scan_studium_tree()
        console.print(f"  Loaded {sum(len(v) for v in self.tree.values())} lectures "
                      f"across {len(self.tree)} semesters from Studium folder.")

    # ------------------------------------------------------------------
    def classify(self, filepath: Path) -> ClassifyResult:
        content = extract_text(filepath)
        return self._llm_classify(filepath.name, content)

    # ------------------------------------------------------------------
    def _llm_classify(self, filename: str, content: str) -> ClassifyResult:
        tree_str = json.dumps(self.tree, ensure_ascii=False, indent=2)
        content_snippet = content if content else "(no readable content — use filename only)"

        prompt = f"""You are a university file organiser.
Given a filename and a content snippet, choose the best semester folder
and lecture subfolder from the available structure below.

Available folder structure (JSON):
{tree_str}

Filename: {filename}
Content snippet:
---
{content_snippet}
---

Respond ONLY with a JSON object — no markdown, no explanation outside it:
{{
  "semester": "<exact semester folder name from the structure>",
  "lecture":  "<exact lecture folder name from that semester>",
  "confidence": <float 0.0-1.0>,
  "reason": "<one sentence, max 15 words>"
}}

Rules:
- Use EXACT folder names as they appear in the structure.
- If nothing matches well, pick the closest one and set confidence below 0.5.
- Never invent folder names that are not in the structure.
"""

        try:
            response = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[{"role": "user", "content": prompt}],
                format="json",
                options={"temperature": 0},
            )
            raw = response["message"]["content"]
            data = json.loads(raw)

            semester = data.get("semester", "")
            lecture  = data.get("lecture",  "")

            # Validate against real folder tree
            if semester not in self.tree:
                return self._fallback(f"Unknown semester '{semester}' returned by LLM")
            if lecture not in self.tree[semester]:
                return self._fallback(
                    f"Lecture '{lecture}' not in {semester}", semester=semester
                )

            result = ClassifyResult(
                semester=semester,
                lecture=lecture,
                confidence=float(data.get("confidence", 0.5)),
                reason=data.get("reason", "LLM classification."),
            )

            if not result.is_confident:
                console.print(
                    f"  [yellow]⚠ Low confidence ({result.confidence:.0%}) — "
                    f"double-check placement[/yellow]"
                )

            return result

        except json.JSONDecodeError as e:
            return self._fallback(f"JSON parse error: {e}")
        except Exception as e:
            return self._fallback(f"LLM call failed: {e}")

    def _fallback(self, reason: str, semester: str = "") -> ClassifyResult:
        """When classification fails, pick the first semester as a safe landing zone."""
        first_sem = semester or (list(self.tree.keys())[0] if self.tree else "")
        console.print(f"  [red]Fallback:[/red] {reason}")
        return ClassifyResult(
            semester=first_sem,
            lecture="_Unsorted",
            confidence=0.0,
            reason=reason,
            error=reason,
        )

    def reload_tree(self) -> None:
        """Call this if you add new semester/lecture folders at runtime."""
        self.tree = scan_studium_tree()
        console.print("  [dim]Folder tree reloaded.[/dim]")