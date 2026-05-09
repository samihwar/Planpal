import copy
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


DATA_DIR = Path(__file__).parent.parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"
logger = logging.getLogger(__name__)


def _load_json_file(path: Path, default: Any) -> Any:
    if not path.exists():
        return copy.deepcopy(default)

    with open(path, "r", encoding="utf-8") as file:
        raw_text = file.read()

    if not raw_text.strip():
        return copy.deepcopy(default)

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.warning("JSON file %s is invalid (%s). Using default value instead.", path, exc)
        return copy.deepcopy(default)


def _save_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(data, indent=2) + "\n"
    with open(path, "w", encoding="utf-8") as file:
        file.write(serialized)


def load_tasks() -> list[dict[str, Any]]:
    return _load_json_file(TASKS_FILE, [])


def save_tasks(tasks: list[dict[str, Any]]) -> None:
    _save_json_file(TASKS_FILE, tasks)


class TaskStorage:
    def __init__(self, filepath: str | Path = TASKS_FILE):
        self.filepath = Path(filepath)

    def load_tasks(self) -> list[dict[str, Any]]:
        return _load_json_file(self.filepath, [])

    def save_tasks(self, tasks: list[dict[str, Any]]) -> None:
        _save_json_file(self.filepath, tasks)

    def add_task(self, task: dict[str, Any]) -> dict[str, Any]:
        tasks = self.load_tasks()
        saved_task = dict(task)
        saved_task.setdefault("id", str(uuid4()))
        saved_task.setdefault("created_at", datetime.now(timezone.utc).isoformat())
        saved_task.setdefault("completed", False)
        saved_task.setdefault("archived", False)
        saved_task.setdefault("project", "project")
        tasks.append(saved_task)
        self.save_tasks(tasks)
        return saved_task

    def update_task(self, task_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
        tasks = self.load_tasks()
        for index, task in enumerate(tasks):
            if str(task.get("id")) == str(task_id):
                updated_task = {**task, **updates, "id": task.get("id", task_id)}
                tasks[index] = updated_task
                self.save_tasks(tasks)
                return updated_task
        return None

    def delete_task(self, task_id: str) -> bool:
        tasks = self.load_tasks()
        remaining_tasks = [task for task in tasks if str(task.get("id")) != str(task_id)]
        if len(remaining_tasks) == len(tasks):
            return False
        self.save_tasks(remaining_tasks)
        return True


