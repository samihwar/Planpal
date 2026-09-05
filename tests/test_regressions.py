"""Run with: python -m unittest discover -s tests -p test_regressions.py"""
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from main import app
from api import routes
from storage import TaskStorage, TASKS_FILE
from task_handler import apply_follow_up_answer


class TaskRegressionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.storage = TaskStorage(Path(self.temp.name) / "tasks.json")
        self.patcher = patch.object(routes, "storage", self.storage)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)
        self.client = TestClient(app)

    def test_create_edit_archive_restore_delete(self):
        response = self.client.post("/api/tasks/confirm", json={"task": {
            "title": "Review", "date": "2026-09-05", "time": "23:45",
            "duration": 3.25, "project": "Work",
        }})
        self.assertEqual(response.status_code, 200)
        task_id = response.json()["task"]["id"]
        for changes in ({"title": "Reviewed", "duration": 2.75},
                        {"completed": True, "archived": True},
                        {"completed": False, "archived": False},
                        {"time": None, "duration": None, "time_mode": "none", "all_day": True}):
            response = self.client.patch(f"/api/tasks/{task_id}", json=changes)
            self.assertEqual(response.status_code, 200)
            for field, value in changes.items():
                self.assertEqual(response.json()["task"][field], value)
        self.assertEqual(len(self.client.get("/api/tasks").json()["tasks"]), 1)
        self.assertEqual(self.client.delete(f"/api/tasks/{task_id}").status_code, 200)
        self.assertEqual(self.client.get("/api/tasks").json()["tasks"], [])
        self.assertEqual(self.client.delete(f"/api/tasks/{task_id}").status_code, 404)

    def test_invalid_confirm_and_patch_do_not_modify_storage(self):
        task = self.storage.add_task({"title": "Valid"})
        before = self.storage.filepath.read_bytes()
        for values in ({"title": " "}, {"title": None}, {"title": 4},
                       {"date": "2026-02-30"}, {"time": "25:00"},
                       {"duration": -1}, {"duration": "NaN"}):
            with self.subTest(values=values):
                response = self.client.post("/api/tasks/confirm", json={"task": {"title": "Valid", **values}})
                self.assertEqual(response.status_code, 422)
                response = self.client.patch(f"/api/tasks/{task['id']}", json=values)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(self.storage.filepath.read_bytes(), before)

    def test_new_tasks_always_receive_unique_ids(self):
        first = self.storage.add_task({"title": "First", "id": None})
        second = self.storage.add_task({"title": "Second", "id": first["id"]})
        self.assertTrue(first["id"])
        self.assertNotEqual(first["id"], second["id"])

    def test_concurrent_creates_preserve_every_task(self):
        class SlowStorage(TaskStorage):
            def load_tasks(self):
                tasks = super().load_tasks()
                time.sleep(0.005)
                return tasks
        # Separate storage instances exercise the shared lock as well.
        def create(index):
            return SlowStorage(self.storage.filepath).add_task({"title": str(index)})
        with ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(create, range(40)))
        self.assertEqual(len(self.storage.load_tasks()), 40)

    def test_failed_write_preserves_previous_file(self):
        self.storage.add_task({"title": "Keep me"})
        before = self.storage.filepath.read_bytes()
        with patch("storage.os.replace", side_effect=OSError("Disk failure")):
            with self.assertRaises(OSError):
                self.storage.add_task({"title": "New"})
        self.assertEqual(self.storage.filepath.read_bytes(), before)
        self.assertEqual(len(list(self.storage.filepath.parent.iterdir())), 1)

    def test_corrupt_file_is_not_overwritten(self):
        self.storage.filepath.write_text('[{"title": "Broken', encoding="utf-8")
        before = self.storage.filepath.read_bytes()
        with self.assertRaises(ValueError):
            self.storage.add_task({"title": "New"})
        self.assertEqual(self.storage.filepath.read_bytes(), before)

    def test_default_path_is_independent_of_working_directory(self):
        self.assertTrue(TASKS_FILE.is_absolute())
        self.assertEqual(TaskStorage().filepath, ROOT / "data" / "tasks.json")

    def test_utf8_bom_task_file_loads_without_rewriting_it(self):
        self.storage.filepath.write_text('[{"id":"existing","title":"Caf\u00e9"}]', encoding="utf-8-sig")
        before = self.storage.filepath.read_bytes()
        response = self.client.get("/api/tasks")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tasks"][0]["title"], "Caf\u00e9")
        self.assertEqual(self.storage.filepath.read_bytes(), before)

    def test_corrupt_storage_returns_json_error_and_preserves_data(self):
        self.storage.filepath.write_text('[{"title":', encoding="utf-8")
        before = self.storage.filepath.read_bytes()
        for response in (self.client.get("/api/tasks"), self.client.post(
            "/api/tasks/confirm", json={"task": {"title": "New task"}}
        )):
            self.assertEqual(response.status_code, 500)
            self.assertIn("application/json", response.headers["content-type"])
            self.assertIn("not been overwritten", response.json()["detail"])
        self.assertEqual(self.storage.filepath.read_bytes(), before)

    def test_date_picker_followup_does_not_require_llm(self):
        with patch("task_handler.resolve_temporal_update", side_effect=AssertionError("LLM called")):
            response = self.client.post("/api/tasks/follow-up", json={
                "task": {"title": "Review", "time": "09:00"},
                "answers": {"date": "2026-09-06"},
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["task"]["date"], "2026-09-06")

    def test_time_followup_accepts_no_time_and_clock_time(self):
        for answer, expected in (("__no_time__", None), ("09:15", "09:15"), ("8 pm", "20:00")):
            task = apply_follow_up_answer({"title": "Review"}, "time", answer)
            self.assertEqual(task["time"], expected)

    def test_followup_rejects_nonpositive_or_nonfinite_duration(self):
        for answer in (0, -1, "NaN", "Infinity", True, None):
            with self.subTest(answer=answer), self.assertRaises(ValueError):
                apply_follow_up_answer({}, "duration", answer)


if __name__ == "__main__":
    unittest.main()
