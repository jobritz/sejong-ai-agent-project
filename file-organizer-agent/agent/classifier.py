"""
agent/classifier.py — content-aware classifier using a local Ollama LLM.

Pipeline:
  1. Extract a text snippet from the file (PDF, DOCX, TXT, …)
  2. Scan the University folder tree to get available semesters + lectures
  3. Ask Ollama to pick the best (semester, lecture) match
  4. Return a ClassifyResult with the target path
"""

from __future__ import annotations
import json
from dataclasses import dataclass
from pathlib import Path

import ollama
import fitz                     # pymupdf
import docx                     # python-docx
from pptx import Presentation   # python-pptx
import base64
from io import BytesIO
from PIL import Image 
from rich.console import Console

from config import (
    OLLAMA_MODEL, OLLAMA_URL,
    MAX_CONTENT_CHARS, READABLE_EXTENSIONS, IMAGE_EXTENSIONS, CONFIDENCE_THRESHOLD,
    TARGET_DIR
)

console = Console()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------
@dataclass
class ClassifyResult:
    target_path: str 
    confidence:  float
    reason:      str
    error:       str = ""
    should_move: bool = True

    @property
    def target_dir(self) -> Path:
        return TARGET_DIR / self.target_path

    @property
    def is_confident(self) -> bool:
        return self.confidence >= CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# Folder scanner
# ---------------------------------------------------------------------------
def scan_folder_tree() -> list[str]:
    """
    Returns a flat list of all subdirectory paths relative to TARGET_DIR.
    Works with any folder structure at any depth.
    """
    if not TARGET_DIR.exists():
        raise FileNotFoundError(
            f"Target folder not found: {TARGET_DIR}\n"
            "Create it first or update TARGET_DIR in config.py"
        )
    return sorted(
        d.relative_to(TARGET_DIR).as_posix()
        for d in TARGET_DIR.rglob("*")
        if d.is_dir() and not d.name.startswith(".")
    )

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
            
        elif ext == {".pptx", ".ppt"}:
            prs = Presentation(str(filepath))
            for slide in prs.slides:
                for shape in slide.shapes:
                    if shape.has_text_frame:
                        for para in shape.text_frame.paragraphs:
                            text += para.text + "\n"
                    if len(text) >= MAX_CONTENT_CHARS:
                        break
                if len(text) >= MAX_CONTENT_CHARS:
                    break

        elif ext in READABLE_EXTENSIONS:
            text = filepath.read_text(encoding="utf-8", errors="ignore")

    except Exception as e:
        console.print(f"  [yellow]Content extract warning:[/yellow] {e}")

    return text[:MAX_CONTENT_CHARS].strip()

def load_image_base64(filepath: Path, max_px: int = 1024) -> str:
    """
    Load an image, downscale it so the longest edge ≤ max_px, and return
    a base64-encoded JPEG string ready for the Ollama vision API.
    Keeping images small is important — large images slow inference
    significantly and provide little extra information for classification.
    """
    with Image.open(filepath) as img:
        img = img.convert("RGB")          # drop alpha, normalise mode
        img.thumbnail((max_px, max_px))   # resize in-place, keeps aspect ratio
        buf = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return base64.b64encode(buf.getvalue()).decode("utf-8")

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
            )

        self.folders = scan_folder_tree()
        console.print(f"  Loaded {len(self.folders)} folders from {TARGET_DIR}.")

    # ------------------------------------------------------------------
    def classify(self, filepath: Path) -> ClassifyResult:
        ext       = filepath.suffix.lower()
        content   = ""
        image_b64 = None

        if ext in IMAGE_EXTENSIONS:
            try:
                image_b64 = load_image_base64(filepath)
            except Exception as e:
                return self._fallback(f"Could not load image: {e}")
        else:
            content = extract_text(filepath)

        return self._llm_classify(filepath.name, content, image_b64)

    # ------------------------------------------------------------------
    def _llm_classify(self, filename: str, content: str = "", image_b64: str | None = None,) -> ClassifyResult:
        folders_str = "\n".join(f"  - {f}" for f in self.folders)

        content_section = (
            "(see attached image)"          if image_b64 else
            content                         if content   else
            "(no readable content — use filename only)"
        )
        
        prompt = f"""You are a file organiser for a student.
Given a filename and a content snippet, choose the best semester folder,
lecture subfolder, and file-type subfolder from the structures below.

Available folders (relative paths):
{folders_str}

Filename: {filename}
Content:
---
{content_section}
---

Respond ONLY with a JSON object — no markdown, no explanation outside it:
{{
  "target_path": "<exact relative folder path from the list of Available folders above>",
  "confidence": <float 0.0-1.0>,
  "reason": "<one sentence, max 15 words>"
}}
"""
        message = (
            {"role": "user", "content": prompt, "images":  [image_b64]}
            if image_b64 else
            {"role": "user", "content": prompt}
        )
        
        try:
            response = self.client.chat(
                model=OLLAMA_MODEL,
                messages=[message],
                format="json",
                options={"temperature": 0},
            )
            data = json.loads(response["message"]["content"])

            target_path = data.get("target_path", "")
            target_path = target_path.replace("\\", "/").replace("//", "/").strip("/")
            
            if target_path not in self.folders:
                return self._fallback(f"Unknown path '{target_path}' not in folder list")

            result = ClassifyResult(
                target_path=target_path,
                confidence=float(data.get("confidence", 0.5)),
                reason=data.get("reason", "LLM classification."),
                should_move=True,
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

    def _fallback(self, reason: str) -> ClassifyResult:
        console.print(f"  [red]Fallback:[/red] {reason}")
        return ClassifyResult(
            target_path="",
            confidence=0.0,
            reason=reason,
            error=reason,
            should_move=False,
        )

    def reload_tree(self) -> None:
        self.folders = scan_folder_tree()
        console.print("  [dim]Folder tree reloaded.[/dim]")