import importlib.util
import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
INTERACTIVE_PATH = PROJECT_ROOT / "tests" / "test_interactive.py"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import feedback as feedback_module
import storage


spec = importlib.util.spec_from_file_location("planpal_test_interactive", INTERACTIVE_PATH)
interactive = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(interactive)


class InteractiveHelperTests(unittest.TestCase):
    def test_parse_error_type_selection_accepts_numbers(self):
        parsed = interactive.parse_error_type_selection("2, 4")

        self.assertEqual(parsed, ["wrong_date", "wrong_duration"])

    def test_fields_for_error_types_returns_only_specific_fields(self):
        fields = interactive.fields_for_error_types(
            ["wrong_time", "unnecessary_followup", "wrong_date", "wrong_time"]
        )

        self.assertEqual(fields, ("time", "date"))

    def test_prompt_corrected_task_only_prompts_target_fields(self):
        parsed_task = {
            "title": "Eat Dinner",
            "description": "Eat dinner next Tuesday",
            "date": "2026-04-21",
            "time": None,
            "duration": 1,
        }

        with patch("builtins.input", side_effect=["19:00"]):
            corrected_task = interactive.prompt_corrected_task(parsed_task, fields=("time",))

        self.assertEqual(
            corrected_task,
            {
                "title": "Eat Dinner",
                "description": "Eat dinner next Tuesday",
                "date": "2026-04-21",
                "time": "19:00",
                "duration": 1,
            },
        )

    def test_prompt_task_correction_for_specific_field_skips_full_task_prompt(self):
        parsed_task = {
            "title": "Eat Dinner",
            "description": "Eat dinner next Tuesday",
            "date": "2026-04-21",
            "time": None,
            "duration": 1,
        }

        with patch("builtins.input", side_effect=["19:00"]):
            corrected_task = interactive.prompt_task_correction_for_error_types(
                parsed_task,
                ["wrong_time"],
            )

        self.assertEqual(corrected_task["time"], "19:00")
        self.assertEqual(corrected_task["date"], "2026-04-21")


class InteractiveSavedDataTests(unittest.TestCase):
    def setUp(self):
        self.feedback_entries = []
        self.user_profiles = {
            "default": {
                "timezone": "Asia/Jerusalem",
                "time_phrase_defaults": {"evening": "19:00"},
                "followup_preference": "ask_when_ambiguous",
                "duration_policy": "never_assume",
            }
        }

        for _ in range(5):
            self.feedback_entries.append(
                {
                    "input_text": "Dinner in the evening",
                    "parsed_task": {
                        "title": "Dinner",
                        "description": "Dinner",
                        "date": None,
                        "time": "18:00",
                        "duration": None,
                    },
                    "user_correct": False,
                    "error_types": ["wrong_time"],
                    "corrected_task": {
                        "title": "Dinner",
                        "description": "Dinner",
                        "date": None,
                        "time": "19:00",
                        "duration": None,
                    },
                    "notes": None,
                    "timestamp": "2026-04-17T18:00:00+00:00",
                    "user_id": "default",
                }
            )

        self.patchers = [
            patch.object(storage, "load_feedback_entries", side_effect=self._load_feedback_entries),
            patch.object(storage, "save_feedback_entries", side_effect=self._save_feedback_entries),
            patch.object(storage, "append_feedback_entry", side_effect=self._append_feedback_entry),
            patch.object(storage, "load_user_profile", side_effect=self._load_user_profile),
            patch.object(storage, "save_user_profile", side_effect=self._save_user_profile),
            patch.object(storage, "load_user_profiles", side_effect=self._load_user_profiles),
            patch.object(storage, "save_user_profiles", side_effect=self._save_user_profiles),
            patch.object(feedback_module, "load_feedback_entries", side_effect=self._load_feedback_entries),
            patch.object(feedback_module, "append_feedback_entry", side_effect=self._append_feedback_entry),
            patch.object(feedback_module, "load_user_profile", side_effect=self._load_user_profile),
            patch.object(feedback_module, "save_user_profile", side_effect=self._save_user_profile),
        ]
        for patcher in self.patchers:
            patcher.start()
            self.addCleanup(patcher.stop)

    def _load_feedback_entries(self):
        return copy.deepcopy(self.feedback_entries)

    def _save_feedback_entries(self, entries):
        self.feedback_entries = copy.deepcopy(entries)

    def _append_feedback_entry(self, entry):
        entry_copy = copy.deepcopy(entry)
        self.feedback_entries.append(entry_copy)
        return copy.deepcopy(entry_copy)

    def _load_user_profiles(self):
        return copy.deepcopy(self.user_profiles)

    def _save_user_profiles(self, profiles):
        self.user_profiles = copy.deepcopy(profiles)

    def _load_user_profile(self, user_id):
        profile = self.user_profiles.get(user_id)
        return copy.deepcopy(profile) if profile is not None else None

    def _save_user_profile(self, user_id, profile):
        profile_copy = copy.deepcopy(profile)
        self.user_profiles[user_id] = profile_copy
        return copy.deepcopy(profile_copy)

    def test_run_manual_parser_test_uses_saved_default_profile_and_adaptive_rules(self):
        captured = {}

        def fake_parse_task(text, backend, **kwargs):
            captured["text"] = text
            captured["backend"] = backend
            captured["kwargs"] = kwargs
            return {
                "title": "Dinner",
                "description": "Dinner in the evening",
                "date": None,
                "time": None,
                "duration": None,
            }

        with patch("task_handler.parse_task", side_effect=fake_parse_task), patch(
            "task_handler.revise_parse",
            return_value={
                "title": "Dinner",
                "description": "Dinner in the evening",
                "date": None,
                "time": "19:00",
                "duration": None,
            },
        ), patch("builtins.input", side_effect=["Dinner in the evening", "yes", ""]):
            interactive.run_manual_parser_test()

        self.assertEqual(captured["text"], "Dinner in the evening")
        self.assertEqual(captured["backend"], "ollama")
        self.assertEqual(captured["kwargs"]["user_profile"]["time_phrase_defaults"]["evening"], "19:00")
        self.assertTrue(captured["kwargs"]["adaptive_rules"])
        self.assertIn("saved time_phrase_defaults", captured["kwargs"]["adaptive_rules"][0])


if __name__ == "__main__":
    unittest.main()
