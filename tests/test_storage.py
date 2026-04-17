import json
import shutil
import sys
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import storage


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.data_dir = PROJECT_ROOT / "tests" / f"_tmp_storage_{uuid.uuid4().hex}"
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.addCleanup(self._cleanup_data_dir)

        self.patches = [
            patch.object(storage, "TASKS_FILE", self.data_dir / "tasks.json"),
            patch.object(storage, "FEEDBACK_FILE", self.data_dir / "feedback.json"),
            patch.object(storage, "USER_PROFILES_FILE", self.data_dir / "user_profiles.json"),
        ]
        for patcher in self.patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _cleanup_data_dir(self):
        shutil.rmtree(self.data_dir, ignore_errors=True)

    def test_load_feedback_entries_returns_default_for_blank_file(self):
        storage.FEEDBACK_FILE.write_text("", encoding="utf-8")

        self.assertEqual(storage.load_feedback_entries(), [])

    def test_load_user_profiles_returns_default_for_invalid_json(self):
        storage.USER_PROFILES_FILE.write_text("{not valid json", encoding="utf-8")

        self.assertEqual(storage.load_user_profiles(), {})

    def test_append_feedback_entry_recovers_from_blank_file_and_persists_json(self):
        storage.FEEDBACK_FILE.write_text("", encoding="utf-8")

        entry = {
            "input_text": "eat dinner tomorrow",
            "parsed_task": {"title": "Eat Dinner"},
            "user_correct": True,
            "error_types": [],
            "corrected_task": None,
            "notes": None,
            "timestamp": "2026-04-17T20:00:00",
            "user_id": "default",
        }

        saved_entry = storage.append_feedback_entry(entry)

        self.assertEqual(saved_entry, entry)
        self.assertEqual(storage.load_feedback_entries(), [entry])
        self.assertEqual(json.loads(storage.FEEDBACK_FILE.read_text(encoding="utf-8")), [entry])


if __name__ == "__main__":
    unittest.main()
