import sys
import unittest
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from task_parser import OllamaBackend


class TaskParserDateConsistencyTests(unittest.TestCase):
    def setUp(self):
        self.backend = OllamaBackend()
        self.reference_now = datetime(2026, 4, 17, 20, 0)

    def test_relative_next_sunday_overrides_wrong_model_date(self):
        parsed = {
            "title": "Eat",
            "description": "Eat next Sunday at 7am for 1 hour",
            "date": "2026-04-24",
            "time": "07:00",
            "duration": 1,
        }

        updated = self.backend._apply_date_consistency_overrides(
            parsed,
            "eat next sunday at 7am for 1 hour",
            self.reference_now,
        )

        self.assertEqual(updated["date"], "2026-04-19")
        self.assertEqual(updated["time"], "07:00")

    def test_relative_next_tuesday_overrides_wrong_model_date(self):
        parsed = {
            "title": "Eat Dinner",
            "description": "next tuesday eat dinner for 1 hour",
            "date": "2026-04-23",
            "time": None,
            "duration": 1,
        }

        updated = self.backend._apply_date_consistency_overrides(
            parsed,
            "next tuesday eat dinner for 1 hour",
            self.reference_now,
        )

        self.assertEqual(updated["date"], "2026-04-21")

    def test_numeric_date_overrides_wrong_model_date(self):
        parsed = {
            "title": "Go out with friends",
            "description": "Go out with friends 23.04.2026 for 3 hours",
            "date": "2026-04-17",
            "time": None,
            "duration": 3,
        }

        updated = self.backend._apply_date_consistency_overrides(
            parsed,
            "go out with friends 23.04.2026 for 3 hours",
            self.reference_now,
        )

        self.assertEqual(updated["date"], "2026-04-23")

    def test_year_first_numeric_date_with_dots_is_supported(self):
        parsed = {
            "title": "Go Hiking with Friends",
            "description": "Go hiking with friends 2026.05.03 for 8 hours",
            "date": "2026-04-17",
            "time": None,
            "duration": 8,
        }

        updated = self.backend._apply_date_consistency_overrides(
            parsed,
            "go hiking with friends 2026.05.03 for 8 hours",
            self.reference_now,
        )

        self.assertEqual(updated["date"], "2026-05-03")

    def test_no_explicit_date_reference_leaves_date_unchanged(self):
        parsed = {
            "title": "Eat Dinner",
            "description": "Eat dinner for 1 hour",
            "date": None,
            "time": None,
            "duration": 1,
        }

        updated = self.backend._apply_date_consistency_overrides(
            parsed,
            "eat dinner for 1 hour",
            self.reference_now,
        )

        self.assertIsNone(updated["date"])

    def test_no_explicit_time_keeps_model_guess(self):
        parsed = {
            "title": "Eat Dinner",
            "description": "next tuesday eat dinner for 1 hour",
            "date": "2026-04-21",
            "time": "20:00",
            "duration": 1,
        }

        updated = self.backend._apply_time_consistency_overrides(
            parsed,
            "next tuesday eat dinner for 1 hour",
        )

        self.assertEqual(updated["time"], "20:00")

    def test_explicit_am_pm_time_is_normalized(self):
        parsed = {
            "title": "Eat",
            "description": "Eat next Sunday at 7am for 1 hour",
            "date": "2026-04-19",
            "time": "19:00",
            "duration": 1,
        }

        updated = self.backend._apply_time_consistency_overrides(
            parsed,
            "eat next sunday at 7am for 1 hour",
        )

        self.assertEqual(updated["time"], "07:00")

    def test_ambiguous_at_hour_keeps_matching_model_time(self):
        parsed = {
            "title": "Play Volleyball",
            "description": "play volleyball at 7 this friday for 1.5 hours",
            "date": "2026-04-17",
            "time": "19:00",
            "duration": 1.5,
        }

        updated = self.backend._apply_time_consistency_overrides(
            parsed,
            "play volleyball at 7 this friday for 1.5 hours",
        )

        self.assertEqual(updated["time"], "19:00")

    def test_profile_time_default_keeps_or_fills_time(self):
        self.backend.user_profile["time_phrase_defaults"]["evening"] = "19:00"
        parsed = {
            "title": "Dinner",
            "description": "Dinner in the evening",
            "date": None,
            "time": None,
            "duration": None,
        }

        updated = self.backend._apply_time_consistency_overrides(
            parsed,
            "dinner in the evening",
        )

        self.assertEqual(updated["time"], "19:00")


if __name__ == "__main__":
    unittest.main()
