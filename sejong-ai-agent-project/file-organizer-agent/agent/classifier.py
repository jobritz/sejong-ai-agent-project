"""
agent/classifier.py — two-stage file classifier.

Stage 1: Fast rule-based lookup by extension  (free, instant).
Stage 2: LLM call for ambiguous files          (paid, ~200ms).

The classifier returns a ClassifyResult dataclass so the rest of the
agent never has to parse raw API responses.
"""

from __future__ import annotations
import json
import os
from dataclasses import dataclass, field
from pathlib import Path

# from openai import OpenAI
from ollama import chat
from rich.console import Console

from config import (
    EXTENSION_MAP,
    AMBIGUOUS_EXTENSIONS,
    CLASSIFIER_SYSTEM_PROMPT,
    CLASSIFIER_USER_TEMPLATE,
    CONFIDENCE_THRESHOLD,
)

console = Console()


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------
@dataclass
class ClassifyResult:
    category:   str
    confidence: float
    reason:     str
    used_llm:   bool = False
    error:      str  = ""

    @property
    def is_confident(self) -> bool:
        return self.confidence >= CONFIDENCE_THRESHOLD


# ---------------------------------------------------------------------------
# Classifier class
# ---------------------------------------------------------------------------
class FileClassifier:
    """
    Wraps rule-based + LLM classification behind a single .classify() method.
    Keeps a simple in-memory token counter so you can estimate API cost.
    """

    def __init__(self, model: str = "llama3"):
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "OPENAI_API_KEY not set. Create a .env file with your key."
            )
        self.client    = OpenAI(api_key=api_key)
        """
        self.model     = model
        self.llm_calls = 0
        self.total_tokens = 0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def classify(self, filepath: Path) -> ClassifyResult:
        """Classify a single file. Always returns a ClassifyResult."""
        ext = filepath.suffix.lower()

        # --- Stage 1: rule-based ---
        if ext in EXTENSION_MAP and ext not in AMBIGUOUS_EXTENSIONS:
            return ClassifyResult(
                category=EXTENSION_MAP[ext],
                confidence=1.0,
                reason="Matched by file extension rule.",
                used_llm=False,
            )

        # --- Stage 2: LLM ---
        return self._llm_classify(filepath.name)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _llm_classify(self, filename: str) -> ClassifyResult:
        """Send filename to the LLM and parse the JSON response."""
        self.llm_calls += 1
        try:
            """
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": CLASSIFIER_USER_TEMPLATE.format(filename=filename),
                    },
                ],
                temperature=0,          # deterministic classification
                max_tokens=120,
                response_format={"type": "json_object"},
            )
            """
            response = chat(
                model="llama3",
                messages=[
                    {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": CLASSIFIER_USER_TEMPLATE.format(filename=filename),
                    },
                ],
                response_format={"type": "json_object"},
            )
            self.total_tokens += response.usage.total_tokens
            raw = response.choices[0].message.content
            data = json.loads(raw)

            result = ClassifyResult(
                category=data.get("category", "misc"),
                confidence=float(data.get("confidence", 0.5)),
                reason=data.get("reason", "LLM classification."),
                used_llm=True,
            )

            # Safety: fall back to misc if confidence too low
            if not result.is_confident:
                console.print(
                    f"  [yellow]⚠ Low confidence ({result.confidence:.0%}) "
                    f"for '{filename}' → misc[/yellow]"
                )
                result.category = "misc"

            return result

        except json.JSONDecodeError as e:
            return ClassifyResult(
                category="misc", confidence=0.0,
                reason="JSON parse error from LLM.",
                used_llm=True, error=str(e),
            )
        except Exception as e:
            return ClassifyResult(
                category="misc", confidence=0.0,
                reason="LLM call failed.",
                used_llm=True, error=str(e),
            )

    def cost_estimate(self) -> str:
        """Rough cost estimate (GPT-4o-mini pricing as of mid-2024)."""
        cost_usd = self.total_tokens * 0.00000015  # ~$0.15 per 1M tokens
        return (
            f"LLM calls: {self.llm_calls} | "
            f"Tokens: {self.total_tokens:,} | "
            f"Est. cost: ${cost_usd:.4f}"
        )
