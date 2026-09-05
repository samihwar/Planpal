import copy
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from threading import RLock
from uuid import uuid4


DATA_DIR = Path(__file__).parent.parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"
# FastAPI dispatches synchronous routes across threads in the server process.
_storage_lock = RLock()


class TaskStorageError(ValueError):
    """Saved task data cannot be read safely."""


def _load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)

    # Windows editors can prepend a BOM; utf-8-sig also reads plain UTF-8.
    with open(path, "r", encoding="utf-8-sig") as file:
        raw_text = file.read()

    if not raw_text.strip():
        return copy.deepcopy(default)

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise TaskStorageError("The saved task file contains invalid JSON. Your data has not been overwritten.") from exc


def _save_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2) + "\n"
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, delete=False) as file:
            temporary_path = Path(file.name)
            file.write(serialized)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def load_tasks() -> list[dict[str, Any]]:
    with _storage_lock:
        return _load_json_file(TASKS_FILE, [])


def save_tasks(tasks: list[dict[str, Any]]) -> None:
    with _storage_lock:
        _save_json_file(TASKS_FILE, tasks)


class TaskStorage:
    def __init__(self, filepath: str | Path = TASKS_FILE):
        self.filepath = Path(filepath)

    def load_tasks(self) -> list[dict[str, Any]]:
        with _storage_lock:
            return _load_json_file(self.filepath, [])

    def save_tasks(self, tasks: list[dict[str, Any]]) -> None:
        with _storage_lock:
            _save_json_file(self.filepath, tasks)

    def add_task(self, task: dict[str, Any]) -> dict[str, Any]:
        with _storage_lock:
            return self._add_task(task)

    def _add_task(self, task: dict[str, Any]) -> dict[str, Any]:
        tasks = self.load_tasks()
        saved_task = dict(task)
        saved_task["id"] = str(uuid4())
        saved_task.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        saved_task.setdefault("completed", False)
        saved_task.setdefault("archived", False)
        saved_task.setdefault("project", "no project")
        tasks.append(saved_task)
        self.save_tasks(tasks)
        return saved_task

    def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        with _storage_lock:
            return self._update_task(task_id, updates)

    def _update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        tasks = self.load_tasks()
        for index, task in enumerate(tasks):
            if str(task.get("id")) == str(task_id):
                updated_task = {**task, **updates, "id": task.get("id", task_id)}
                tasks[index] = updated_task
                self.save_tasks(tasks)
                return updated_task
        return None

    def delete_task(self, task_id: str) -> bool:
        with _storage_lock:
            return self._delete_task(task_id)

    def _delete_task(self, task_id: str) -> bool:
        tasks = self.load_tasks()
        remaining_tasks = [task for task in tasks if str(task.get("id")) != str(task_id)]
        if len(remaining_tasks) == len(tasks):
            return False
        self.save_tasks(remaining_tasks)
        return True


