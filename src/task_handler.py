from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, List, Mapping

from task_parser import parse_task, resolve_temporal_update


OPTIONAL_SCHEDULING_FIELDS = ("date", "time", "duration")


def normalize_task(task: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "title": task.get("title") or "",
        "description": task.get("description") or "",
        "date": task.get("date"),
        "time": task.get("time"),
        "duration": task.get("duration"),
    }


def _resolve_reference_now(reference_now: datetime | None = None) -> datetime:
    return reference_now or datetime.now()


def _next_occurrence_date(time_text: str, reference_now: datetime | None = None) -> str:
    current = _resolve_reference_now(reference_now)
    parsed_time = datetime.strptime(time_text, "%H:%M").time()
    candidate = datetime.combine(current.date(), parsed_time)
    if candidate <= current:
        candidate = candidate + timedelta(days=1)
    return candidate.strftime("%Y-%m-%d")


def infer_missing_date_from_time(
    task: Dict[str, Any],
    reference_now: datetime | None = None,
) -> Dict[str, Any]:
    updated = dict(task)
    if updated.get("time") and updated.get("date") is None:
        updated["date"] = _next_occurrence_date(updated["time"], reference_now=reference_now)
    return updated


def find_missing_info(
    task: Dict[str, Any],
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
) -> List[str]:
    return [field for field in fields if task.get(field) is None]


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
) -> Dict[str, Any]:
    refreshed = infer_missing_date_from_time(task, reference_now=reference_now)
    refreshed["missing_info"] = find_missing_info(refreshed, fields=fields)
    refreshed["follow_up_questions"] = build_follow_up_questions(refreshed, fields=fields)
    return refreshed


def next_missing_field(
    task: Dict[str, Any],
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
) -> str | None:
    missing = find_missing_info(task, fields=fields)
    return missing[0] if missing else None


def update_task_fields(
    task: Dict[str, Any],
    updates: Mapping[str, Any],
    reference_now: datetime | None = None,
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
) -> Dict[str, Any]:
    invalid_fields = set(updates) - set(fields)
    if invalid_fields:
        invalid = ", ".join(sorted(invalid_fields))
        raise ValueError(f"Unsupported field update: {invalid}")

    updated = dict(task)
    updated.update(updates)
    return refresh_task_state(updated, reference_now=reference_now, fields=fields)


def update_task_field(
    task: Dict[str, Any],
    field: str,
    value: Any,
    reference_now: datetime | None = None,
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
) -> Dict[str, Any]:
    return update_task_fields(
        task,
        {field: value},
        reference_now=reference_now,
        fields=fields,
    )


def apply_follow_up_answer(
    task: Dict[str, Any],
    field: str,
    answer: Any,
    backend: str = "ollama",
    reference_now: datetime | None = None,
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
    **kwargs,
) -> Dict[str, Any]:
    if field == "duration":
        value = answer
        if isinstance(answer, str):
            value = float(answer)
        return update_task_field(
            task,
            field,
            value,
            reference_now=reference_now,
            fields=fields,
        )

    if field in {"date", "time"}:
        resolved = resolve_temporal_update(task, str(answer), backend=backend, **kwargs)
        updates = {}
        if "date" in resolved:
            updates["date"] = resolved["date"]
        if "time" in resolved:
            updates["time"] = resolved["time"]
        return update_task_fields(
            task,
            updates,
            reference_now=reference_now,
            fields=fields,
        )

    return update_task_field(
        task,
        field,
        answer,
        reference_now=reference_now,
        fields=fields,
    )


def parse_task_with_missing_info(
    text: str,
    backend: str = "ollama",
    reference_now: datetime | None = None,
    fields: Iterable[str] = OPTIONAL_SCHEDULING_FIELDS,
    **kwargs,
) -> Dict[str, Any]:
    parsed = parse_task(text, backend=backend, **kwargs)
    normalized = normalize_task(parsed)
    return refresh_task_state(normalized, reference_now=reference_now, fields=fields)
