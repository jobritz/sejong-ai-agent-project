# config.py
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WATCH_DIR   = Path.home() / "Downloads"
TARGET_DIR = Path.home() / "Desktop/University"
LOG_DIR = Path(__file__).parent.resolve() / "log"

# ---------------------------------------------------------------------------
# Ollama (local LLM)
# ---------------------------------------------------------------------------
OLLAMA_MODEL = "gemma4:e4b"
OLLAMA_URL   = "http://localhost:11434"

# ---------------------------------------------------------------------------
# Content extraction
# ---------------------------------------------------------------------------
MAX_CONTENT_CHARS = 3000   # how many chars to send to the LLM (keeps it fast)

# File types we try to read content from
READABLE_EXTENSIONS = {
    ".pdf", ".txt", ".md", ".py", ".js", ".ts", ".java",
    ".cpp", ".c", ".h", ".html", ".css", ".csv",
    ".docx", ".doc", ".pptx", ".ppt",
}

IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".heic",
}

# ---------------------------------------------------------------------------
# Agent behaviour
# ---------------------------------------------------------------------------
MIN_FILE_AGE_SECONDS = 2
MAX_UNDO_STACK       = 50
SUMMARY_HOUR         = 18
CONFIDENCE_THRESHOLD = 0.81