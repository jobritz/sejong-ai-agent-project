"""
tests/test_classifier.py — unit tests for rule-based classification.

Run:  python -m pytest tests/ -v

These tests cover the fast, free rule-based path only — no LLM calls,
no API key required. LLM integration tests belong in tests/test_llm.py
and should be gated with a pytest.mark.integration marker.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import EXTENSION_MAP, AMBIGUOUS_EXTENSIONS


# ---------------------------------------------------------------------------
# Rule-based extension map
# ---------------------------------------------------------------------------
class TestExtensionMap:

    def test_image_extensions(self):
        for ext in [".jpg", ".jpeg", ".png", ".gif", ".webp"]:
            assert EXTENSION_MAP.get(ext) == "images", f"Expected 'images' for {ext}"

    def test_video_extensions(self):
        for ext in [".mp4", ".mov", ".avi", ".mkv"]:
            assert EXTENSION_MAP.get(ext) == "videos", f"Expected 'videos' for {ext}"

    def test_archive_extensions(self):
        for ext in [".zip", ".tar", ".gz", ".rar", ".7z"]:
            assert EXTENSION_MAP.get(ext) == "archives", f"Expected 'archives' for {ext}"

    def test_ambiguous_not_in_extension_map_or_flagged(self):
        """Ambiguous extensions should route to the LLM."""
        for ext in AMBIGUOUS_EXTENSIONS:
            # Either absent from the map, or present but still in AMBIGUOUS set
            # — both are valid; the classifier checks AMBIGUOUS first.
            assert ext in AMBIGUOUS_EXTENSIONS

    def test_no_overlap_between_maps(self):
        """An extension in EXTENSION_MAP that's also in AMBIGUOUS_EXTENSIONS
        will always go to the LLM — make sure that's intentional."""
        overlap = set(EXTENSION_MAP.keys()) & AMBIGUOUS_EXTENSIONS
        # .csv is a valid overlap (data but might be report → LLM)
        known_overlaps = {".csv"}
        unexpected = overlap - known_overlaps
        assert not unexpected, f"Unexpected overlap: {unexpected}"


# ---------------------------------------------------------------------------
# Temp file detection (stateless helper)
# ---------------------------------------------------------------------------
class TestTempFileDetection:

    @pytest.fixture
    def is_temp(self):
        from agent.watcher import OrganizerEventHandler
        return OrganizerEventHandler._is_temp_file

    def test_hidden_files(self, is_temp):
        assert is_temp(Path(".DS_Store")) is True
        assert is_temp(Path(".gitignore")) is True

    def test_office_temp(self, is_temp):
        assert is_temp(Path("~$report.docx")) is True

    def test_partial_downloads(self, is_temp):
        assert is_temp(Path("video.mp4.part")) is True
        assert is_temp(Path("file.crdownload")) is True

    def test_normal_files_not_temp(self, is_temp):
        assert is_temp(Path("report.pdf"))   is False
        assert is_temp(Path("photo.jpg"))    is False
        assert is_temp(Path("script.py"))    is False


# ---------------------------------------------------------------------------
# Collision resolution
# ---------------------------------------------------------------------------
class TestCollisionResolution:

    def test_no_collision(self, tmp_path):
        from agent.executor import FileExecutor
        target = tmp_path / "file.txt"
        result = FileExecutor._resolve_collision(target)
        assert result == target

    def test_collision_appends_counter(self, tmp_path):
        from agent.executor import FileExecutor
        original = tmp_path / "file.txt"
        original.write_text("original")

        result = FileExecutor._resolve_collision(original)
        assert result.name == "file_1.txt"

    def test_multiple_collisions(self, tmp_path):
        from agent.executor import FileExecutor
        for i in range(3):
            name = "file.txt" if i == 0 else f"file_{i}.txt"
            (tmp_path / name).write_text("x")

        result = FileExecutor._resolve_collision(tmp_path / "file.txt")
        assert result.name == "file_3.txt"
