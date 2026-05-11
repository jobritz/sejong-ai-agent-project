"""
config.py — category rules and folder mappings for the file organizer agent.
Edit CATEGORIES to add your own rules before the LLM even gets called.
"""

# ---------------------------------------------------------------------------
# Folder names that will be created inside WATCH_DIR
# ---------------------------------------------------------------------------
CATEGORY_FOLDERS = {
    "images": "📷 Images",
    "videos": "🎬 Videos",
    "audio": "🎵 Audio",
    "documents": "📄 Documents",
    "spreadsheets":"📊 Spreadsheets",
    "code": "💻 Code",
    "archives": "📦 Archives",
    "ebooks": "📚 eBooks",
    "design": "🎨 Design",
    "data": "🗃️ Data",
    "misc": "🗂️ Misc",
}

# ---------------------------------------------------------------------------
# Rule-based pre-classifier  (extension → category)
# Files matching these rules skip the LLM call entirely (saves API cost).
# ---------------------------------------------------------------------------
EXTENSION_MAP = {
    # images
    ".jpg": "images", ".jpeg": "images", ".png": "images",
    ".gif": "images", ".webp": "images", ".svg": "images",
    ".heic": "images", ".bmp": "images", ".tiff": "images",
    # videos
    ".mp4": "videos", ".mov": "videos", ".avi": "videos",
    ".mkv": "videos", ".webm": "videos",
    # audio
    ".mp3": "audio", ".wav": "audio", ".flac": "audio",
    ".aac": "audio", ".ogg": "audio", ".m4a": "audio",
    # archives
    ".zip": "archives", ".tar": "archives", ".gz": "archives",
    ".rar": "archives", ".7z": "archives",
    # ebooks
    ".epub": "ebooks", ".mobi": "ebooks",
    # data
    ".csv": "data", ".json": "data", ".xml": "data",
    ".parquet": "data", ".db": "data", ".sqlite": "data",
    # spreadsheets
    ".xlsx": "spreadsheets", ".xls": "spreadsheets", ".ods": "spreadsheets",
    # design
    ".psd": "design", ".ai": "design", ".fig": "design",
    ".sketch": "design", ".xd": "design",
}

# ---------------------------------------------------------------------------
# These extensions are "ambiguous" — we always ask the LLM for these.
# The filename/content matter more than the extension alone.
# ---------------------------------------------------------------------------
AMBIGUOUS_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt",
    ".md", ".rtf", ".py", ".js", ".ts", ".java", ".cpp",
    ".c", ".h", ".go", ".rs", ".rb", ".sh", ".bat",
    ".html", ".css", ".yml", ".yaml", ".toml", ".ini", ".cfg",
}

# ---------------------------------------------------------------------------
# LLM prompt template
# ---------------------------------------------------------------------------
CLASSIFIER_SYSTEM_PROMPT = """You are a file organisation assistant.
Given a filename, return ONLY a JSON object with these fields:
- "category": one of {categories}
- "confidence": float 0.0–1.0
- "reason": one short sentence (max 12 words)

Rules:
- Choose the most specific category that fits.
- If the file is source code, use "code".
- If genuinely unclear, use "misc".
- Never return anything except the JSON object.
""".format(categories=list(CATEGORY_FOLDERS.keys()))

CLASSIFIER_USER_TEMPLATE = 'Classify this file: "{filename}"'

# ---------------------------------------------------------------------------
# Agent behaviour settings
# ---------------------------------------------------------------------------
CONFIDENCE_THRESHOLD = 0.70  # below this → move to misc, log a warning
MIN_FILE_AGE_SECONDS = 2  # ignore files still being written (partial downloads)
MAX_UNDO_STACK = 50  # max number of moves we can roll back
SUMMARY_HOUR = 18  # hour of day to print the daily summary (24h)
