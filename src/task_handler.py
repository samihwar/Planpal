from datetime import datetime
from typing import Any, Dict, Iterable, List, Mapping
import math
import re

from task_parser import normalize_user_profile, parse_task, resolve_temporal_update, revise_parse


OPTIONAL_SCHEDULING_FIELDS = ("date", "time", "duration")
DEFAULT_USER_ID = "default"
DEFAULT_PROJECT_NAME = "no project"
NO_TIME_ANSWERS = {"__no_time__", "no time", "none", "no", "notime"}
SIMPLE_HOUR_PATTERN = re.compile(r"^\s*(?P<hour>\d{1,2})\s*$")
SIMPLE_TIME_PATTERN = re.compile(r"^\s*(?P<hour>\d{1,2}):(?P<minute>\d{1,2})\s*$")
AM_PM_TIME_PATTERN = re.compile(
    r"^\s*(?P<hour>1[0-2]|0?\d)(?::(?P<minute>[0-5]?\d))?\s*(?P<meridiem>am|pm)\s*$",
    re.IGNORECASE,
)


def normalize_task(task: Dict[str, Any]) -> Dict[str, Any]:
    time = task.get("time")
    project = str(task.get("project") or "").strip()
    if not project or project.lower() == "project":
        project = DEFAULT_PROJECT_NAME
    return {
        "title": task.get("title") or "",
        "description": task.get("description") or "",
        "date": task.get("date"),
        "time": time,
        "time_mode": task.get("time_mode") or ("timed" if time else "none"),
        "duration": task.get("duration"),
        "all_day": bool(task.get("all_day", False)),
        "project": project,
        "archived": bool(task.get("archived", False)),
    }


def _merge_missing_fields(current_task: Dict[str, Any], revised_task: Dict[str, Any]) -> Dict[str, Any]:
    merged_task = dict(current_task)
    for field in ("title", "description", "date", "time", "duration", "project"):
        if merged_task.get(field) in {None, ""} and revised_task.get(field) not in {None, ""}:
            merged_task[field] = revised_task[field]
    return merged_task

def infer_missing_date_from_time(
    task: Dict[str, Any],
    reference_now: datetime | None = None,
) -> Dict[str, Any]:
    return dict(task)


def find_missing_info(
    task: Dict[str, Any],
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
) -> List[str]:
    missing = []
    for field in fields:
        if field == "time" and task.get("time_mode") == "none":
            continue
        if field == "duration" and task.get("all_day"):
            continue
        if task.get(field) is None:
            missing.append(field)
    return missing


def build_follow_up_questions(
    task: Dict[str, Any],
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
) -> List[Dict[str, str]]:
    return [{"field": field} for field in find_missing_info(task, fields=fields)]


def build_missing_info_questions(
    task: Dict[str, Any],
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
) -> List[Dict[str, str]]:
    return build_follow_up_questions(task, fields=fields)


def refresh_task_state(
    task: Dict[str, Any],
    reference_now: datetime | None = None,
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
    followup_preference: str = "ask_when_ambiguous",
) -> Dict[str, Any]:
    active_fields = tuple(fields)
    if followup_preference == "avoid_optional_followups":
        active_fields = tuple(field for field in active_fields if field != "duration")

    refreshed = infer_missing_date_from_time(task, reference_now=reference_now)
    refreshed["missing_info"] = find_missing_info(refreshed, fields=active_fields)
    refreshed["follow_up_questions"] = build_follow_up_questions(refreshed, fields=active_fields)
    return refreshed


def next_missing_field(
    task: Dict[str, Any],
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
    followup_preference: str = "ask_when_ambiguous",
) -> str | None:
    active_fields = tuple(fields)
    if followup_preference == "avoid_optional_followups":
        active_fields = tuple(field for field in active_fields if field != "duration")

    missing = find_missing_info(task, fields=active_fields)
    return missing[0] if missing else None


def update_task_fields(
    task: Dict[str, Any],
    updates: Mapping[str, Any],
    reference_now: datetime | None = None,
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
    followup_preference: str = "ask_when_ambiguous",
) -> Dict[str, Any]:
    invalid_fields = set(updates) - set(fields)
    if invalid_fields:
        invalid = ", ".join(sorted(invalid_fields))
        raise ValueError(f"Unsupported field update: {invalid}")

    updated = dict(task)
    updated.update(updates)
    return refresh_task_state(
        updated,
        reference_now=reference_now,
        fields=fields,
        followup_preference=followup_preference,
    )


def update_task_field(
    task: Dict[str, Any],
    field: str,
    value: Any,
    reference_now: datetime | None = None,
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
    followup_preference: str = "ask_when_ambiguous",
) -> Dict[str, Any]:
    return update_task_fields(
        task,
        {field: value},
        reference_now=reference_now,
        fields=fields,
        followup_preference=followup_preference,
    )


def apply_follow_up_answer(
    task: Dict[str, Any],
    field: str,
    answer: Any,
    backend: str = "ollama",
    reference_now: datetime | None = None,
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
    followup_preference: str = "ask_when_ambiguous",
    **kwargs,
) -> Dict[str, Any]:
    if field == "duration":
        try:
            value = float(answer)
        except (TypeError, ValueError) as exc:
            raise ValueError("Duration must be a positive number of hours") from exc
        if isinstance(answer, bool) or not math.isfinite(value) or value <= 0:
            raise ValueError("Duration must be a positive number of hours")
        return update_task_field(
            task,
            field,
            value,
            reference_now=reference_now,
            fields=fields,
            followup_preference=followup_preference,
        )

    if field in {"date", "time"}:
        if field == "date" and isinstance(answer, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", answer.strip()):
            value = datetime.strptime(answer.strip(), "%Y-%m-%d").date().isoformat()
            return update_task_field(
                task, field, value, reference_now=reference_now,
                fields=fields, followup_preference=followup_preference,
            )
        if field == "time":
            if isinstance(answer, str) and answer.strip().lower() in NO_TIME_ANSWERS:
                updated = dict(task)
                updated["time"] = None
                updated["time_mode"] = "none"
                return refresh_task_state(
                    updated,
                    reference_now=reference_now,
                    fields=fields,
                    followup_preference=followup_preference,
                )

            normalized_time = _normalize_simple_time_answer(answer)
            if normalized_time is not None:
                updated = dict(task)
                updated["time"] = normalized_time
                updated["time_mode"] = "timed"
                return refresh_task_state(
                    updated,
                    reference_now=reference_now,
                    fields=fields,
                    followup_preference=followup_preference,
                )

        resolved = resolve_temporal_update(task, str(answer), backend=backend, **kwargs)
        updates = {}

        if field == "date" and "date" in resolved:
            updates["date"] = resolved["date"]
        if field == "time" and "time" in resolved:
            updates["time"] = resolved["time"]
            updates["time_mode"] = "timed"
        if "time_mode" in updates:
            updated = dict(task)
            updated.update(updates)
            return refresh_task_state(
                updated,
                reference_now=reference_now,
                fields=fields,
                followup_preference=followup_preference,
            )
        return update_task_fields(
            task,
            updates,
            reference_now=reference_now,
            fields=fields,
            followup_preference=followup_preference,
        )

    return update_task_field(
        task,
        field,
        answer,
        reference_now=reference_now,
        fields=fields,
        followup_preference=followup_preference,
    )


def _normalize_simple_time_answer(answer: Any) -> str | None:
    if isinstance(answer, (int, float)):
        hour = int(answer)
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"
        return None

    if not isinstance(answer, str):
        return None

    match = SIMPLE_HOUR_PATTERN.fullmatch(answer)
    if match is not None:
        hour = int(match.group("hour"))
        if 0 <= hour <= 23:
            return f"{hour:02d}:00"
        return None

    match = SIMPLE_TIME_PATTERN.fullmatch(answer)
    if match is not None:
        hour = int(match.group("hour"))
        minute = int(match.group("minute"))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
        return None

    match = AM_PM_TIME_PATTERN.fullmatch(answer)
    if match is not None:
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        meridiem = match.group("meridiem").lower()
        if meridiem == "am":
            hour = 0 if hour == 12 else hour
        else:
            hour = 12 if hour == 12 else hour + 12
        return f"{hour:02d}:{minute:02d}"

    return None


def parse_task_with_missing_info(
    text: str,
    backend: str = "ollama",
    reference_now: datetime | None = None,
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
    user_id: str = DEFAULT_USER_ID,
    user_profile: Mapping[str, Any] | None = None,
    **kwargs,
) -> Dict[str, Any]:
    effective_profile = normalize_user_profile(user_profile)
    adaptive_rules = list(kwargs.pop("adaptive_rules", []))
    initial_parse = parse_task(text, backend=backend, **kwargs)
    normalized = normalize_task(initial_parse)
    refreshed = refresh_task_state(
        normalized,
        reference_now=reference_now,
        fields=fields,
        followup_preference=effective_profile["followup_preference"],
    )

    if refreshed["missing_info"]:
        try:
            revised_parse = revise_parse(
                text,
                normalized,
                backend=backend,
                user_profile=effective_profile,
                adaptive_rules=adaptive_rules,
                **kwargs,
            )
        except Exception:
            revised_parse = None

        if revised_parse is not None:
            normalized = _merge_missing_fields(normalized, normalize_task(revised_parse))
            refreshed = refresh_task_state(
                normalized,
                reference_now=reference_now,
                fields=fields,
                followup_preference=effective_profile["followup_preference"],
            )

    refreshed["user_id"] = user_id
    refreshed["user_profile"] = effective_profile
    refreshed["adaptive_rules"] = adaptive_rules
    return refreshed
