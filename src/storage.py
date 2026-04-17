import copy
import json
import logging
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).parent.parent / "data"
TASKS_FILE = DATA_DIR / "tasks.json"
FEEDBACK_FILE = DATA_DIR / "feedback.json"
USER_PROFILES_FILE = DATA_DIR / "user_profiles.json"
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


def load_feedback_entries() -> list[dict[str, Any]]:
    return _load_json_file(FEEDBACK_FILE, [])


def save_feedback_entries(entries: list[dict[str, Any]]) -> None:
    _save_json_file(FEEDBACK_FILE, entries)


def append_feedback_entry(entry: dict[str, Any]) -> dict[str, Any]:
    entries = load_feedback_entries()
    entries.append(entry)
    save_feedback_entries(entries)
    return entry


def load_user_profiles() -> dict[str, dict[str, Any]]:
    return _load_json_file(USER_PROFILES_FILE, {})


def save_user_profiles(profiles: dict[str, dict[str, Any]]) -> None:
    _save_json_file(USER_PROFILES_FILE, profiles)


def load_user_profile(user_id: str) -> dict[str, Any] | None:
    return load_user_profiles().get(user_id)


def save_user_profile(user_id: str, profile: dict[str, Any]) -> dict[str, Any]:
    profiles = load_user_profiles()
    profiles[user_id] = profile
    save_user_profiles(profiles)
    return profile
