import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import feedback as feedback_module
import storage
from feedback import record_feedback
from task_handler import apply_follow_up_answer, parse_task_with_missing_info, submit_task_feedback
from task_parser import OpenAIBackend


class FeedbackSystemTests(unittest.TestCase):
    def setUp(self):
        self.feedback_entries = []
        self.user_profiles = {}

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

    def test_submit_task_feedback_applies_immediate_fix_and_stores_feedback(self):
        parsed_task = {
            "title": "Dinner",
            "description": "Dinner with family",
            "date": "2026-04-17",
            "time": "18:00",
            "duration": None,
        }
        corrected_task = {
            "title": "Dinner",
            "description": "Dinner with family",
            "date": "2026-04-17",
            "time": "19:00",
            "duration": None,
        }

        result = submit_task_feedback(
            input_text="Dinner in the evening",
            parsed_task=parsed_task,
            user_correct=False,
            user_id="sam",
            error_types=["wrong_time"],
            corrected_task=corrected_task,
            notes="Evening should mean 19:00 for this user.",
        )

        self.assertEqual(result["time"], "19:00")
        self.assertEqual(len(storage.load_feedback_entries()), 1)
        self.assertEqual(storage.load_feedback_entries()[0]["error_types"], ["wrong_time"])

    def test_three_repeated_followup_corrections_suggest_preference(self):
        last_result = None
        for _ in range(3):
            last_result = record_feedback(
                input_text="Workout tomorrow",
                parsed_task={
                    "title": "Workout",
                    "description": "Workout",
                    "date": None,
                    "time": None,
                    "duration": None,
                },
                user_correct=False,
                user_id="sam",
                error_types=["unnecessary_followup"],
                corrected_task={
                    "title": "Workout",
                    "description": "Workout",
                    "date": "2026-04-18",
                    "time": None,
                    "duration": None,
                },
            )

        self.assertIsNotNone(last_result)
        suggestion_fields = {item["field"] for item in last_result["suggested_profile_updates"]}
        self.assertIn("followup_preference", suggestion_fields)
        self.assertEqual(last_result["user_profile"]["followup_preference"], "ask_when_ambiguous")

    def test_five_repeated_time_phrase_corrections_auto_update_profile(self):
        last_result = None
        for _ in range(5):
            last_result = record_feedback(
                input_text="Dinner in the evening",
                parsed_task={
                    "title": "Dinner",
                    "description": "Dinner",
                    "date": None,
                    "time": "18:00",
                    "duration": None,
                },
                user_correct=False,
                user_id="sam",
                error_types=["wrong_time"],
                corrected_task={
                    "title": "Dinner",
                    "description": "Dinner",
                    "date": None,
                    "time": "19:00",
                    "duration": None,
                },
            )

        self.assertIsNotNone(last_result)
        self.assertEqual(last_result["applied_profile_updates"]["time_phrase_defaults"]["evening"], "19:00")
        saved_profile = storage.load_user_profile("sam")
        self.assertEqual(saved_profile["time_phrase_defaults"]["evening"], "19:00")

    def test_parse_task_with_missing_info_uses_profile_and_adaptive_rules(self):
        for _ in range(5):
            record_feedback(
                input_text="Call mom later",
                parsed_task={
                    "title": "Call mom",
                    "description": "Call mom",
                    "date": None,
                    "time": None,
                    "duration": None,
                },
                user_correct=False,
                user_id="sam",
                error_types=["missing_followup"],
                corrected_task={
                    "title": "Call mom",
                    "description": "Call mom",
                    "date": "2026-04-18",
                    "time": "09:00",
                    "duration": None,
                },
            )

        captured = {}

        def fake_parse_task(text, backend, **kwargs):
            captured["text"] = text
            captured["backend"] = backend
            captured["kwargs"] = kwargs
            return {
                "title": "Call mom",
                "description": "Call mom",
                "date": None,
                "time": "19:00",
                "duration": None,
            }

        with patch("task_handler.parse_task", side_effect=fake_parse_task), patch(
            "task_handler.revise_parse",
            return_value={
                "title": "Call mom",
                "description": "Call mom",
                "date": None,
                "time": "19:00",
                "duration": None,
            },
        ):
            result = parse_task_with_missing_info(
                "Call mom in the evening",
                user_id="sam",
                user_profile={
                    "timezone": "Asia/Jerusalem",
                    "time_phrase_defaults": {"evening": "19:00"},
                    "followup_preference": "ask_when_ambiguous",
                    "duration_policy": "never_assume",
                },
            )

        self.assertEqual(captured["backend"], "ollama")
        self.assertEqual(captured["kwargs"]["user_profile"]["time_phrase_defaults"]["evening"], "19:00")
        self.assertTrue(captured["kwargs"]["adaptive_rules"])
        self.assertIn("date", result["missing_info"])
        self.assertEqual(result["feedback_request"]["question"], "Was this correct?")

    def test_parse_task_with_missing_info_runs_revision_before_followup(self):
        with patch(
            "task_handler.parse_task",
            return_value={
                "title": "Eat dinner",
                "description": "eat dinner next tusday",
                "date": None,
                "time": None,
                "duration": None,
            },
        ), patch(
            "task_handler.revise_parse",
            return_value={
                "title": "Eat dinner",
                "description": "eat dinner next tusday",
                "date": "2026-04-21",
                "time": None,
                "duration": None,
            },
        ) as revision_mock:
            result = parse_task_with_missing_info("eat dinner next tusday", user_id="sam")

        revision_mock.assert_called_once()
        self.assertEqual(result["date"], "2026-04-21")
        self.assertNotIn("date", result["missing_info"])

    def test_date_followup_answer_does_not_invent_time(self):
        task = {
            "title": "Eat dinner",
            "description": "Eat dinner",
            "date": None,
            "time": None,
            "duration": 1,
            "missing_info": ["date"],
            "follow_up_questions": [{"field": "date"}],
        }

        with patch(
            "task_handler.resolve_temporal_update",
            return_value={"date": "2026-04-21", "time": "20:00"},
        ):
            updated = apply_follow_up_answer(task, "date", "next tuesday")

        self.assertEqual(updated["date"], "2026-04-21")
        self.assertIsNone(updated["time"])

    def test_time_followup_answer_numeric_hour_is_normalized_locally(self):
        task = {
            "title": "Go hiking with friends",
            "description": "Go hiking with friends",
            "date": "2026-05-03",
            "time": None,
            "duration": 8,
            "missing_info": ["time"],
            "follow_up_questions": [{"field": "time"}],
        }

        with patch("task_handler.resolve_temporal_update") as resolve_mock:
            updated = apply_follow_up_answer(task, "time", "7")

        resolve_mock.assert_not_called()
        self.assertEqual(updated["time"], "07:00")

    def test_time_followup_answer_am_pm_is_normalized_locally(self):
        task = {
            "title": "Go hiking with friends",
            "description": "Go hiking with friends",
            "date": "2026-05-03",
            "time": None,
            "duration": 8,
            "missing_info": ["time"],
            "follow_up_questions": [{"field": "time"}],
        }

        with patch("task_handler.resolve_temporal_update") as resolve_mock:
            updated = apply_follow_up_answer(task, "time", "7pm")

        resolve_mock.assert_not_called()
        self.assertEqual(updated["time"], "19:00")

    def test_openai_prompt_includes_user_profile_and_no_guess_rule(self):
        backend = OpenAIBackend(
            api_key="test-key",
            user_profile={
                "timezone": "Asia/Jerusalem",
                "time_phrase_defaults": {"evening": "19:00"},
                "followup_preference": "ask_when_ambiguous",
                "duration_policy": "never_assume",
            },
            adaptive_rules=["Keep unresolved scheduling fields null."],
        )

        prompt = backend._build_prompt("Dinner in the evening", "2026-04-17 18:00")

        self.assertIn('"timezone": "Asia/Jerusalem"', prompt)
        self.assertIn('"evening": "19:00"', prompt)
        self.assertIn("If the user gives only a date or day reference and no time, set time to null", prompt)
        self.assertIn("Never infer a time from the type of activity alone", prompt)
        self.assertIn("Keep unresolved scheduling fields null.", prompt)

    def test_openai_prompt_mentions_confident_date_and_time_expressions(self):
        backend = OpenAIBackend(api_key="test-key")

        prompt = backend._build_prompt("meet friends at 10 morning tmrw", "2026-04-17 18:00")

        self.assertIn("Convert any date expression you can confidently understand into the date field", prompt)
        self.assertIn("Convert any time expression you can confidently understand into the time field", prompt)
        self.assertIn("If a time is given without a date", prompt)

    def test_openai_revision_prompt_mentions_followup_reduction(self):
        backend = OpenAIBackend(api_key="test-key")

        prompt = backend._build_revision_prompt(
            "eat dinner next tusday",
            {
                "title": "Eat dinner",
                "description": "eat dinner next tusday",
                "date": None,
                "time": None,
                "duration": None,
            },
            "2026-04-17 18:00",
        )

        self.assertIn("avoid unnecessary follow-up questions", prompt)
        self.assertIn("Only fill a missing field", prompt)
        self.assertIn("If the user gives only a date or day reference and no time, keep time null", prompt)
        self.assertIn("Never infer a time from the type of activity alone", prompt)


if __name__ == "__main__":
    unittest.main()
