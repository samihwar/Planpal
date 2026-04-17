from collections import Counter
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from storage import (
    append_feedback_entry,
    load_feedback_entries,
    load_user_profile,
    save_user_profile,
)


ERROR_TYPES = (
    "wrong_title",
    "wrong_date",
    "wrong_time",
    "wrong_duration",
    "missing_field_not_detected",
    "unnecessary_followup",
    "missing_followup",
    "misunderstood_text",
)
ERROR_TYPE_SET = set(ERROR_TYPES)
DEFAULT_FOLLOWUP_PREFERENCE = "ask_when_ambiguous"
DEFAULT_DURATION_POLICY = "never_assume"
SUGGESTION_THRESHOLD = 3
AUTO_APPLY_THRESHOLD = 5
KNOWN_TIME_PHRASES = (
    "morning",
    "afternoon",
    "evening",
    "night",
    "tonight",
    "noon",
)


def _default_timezone() -> str:
    try:
        from tzlocal import get_localzone_name

        return str(get_localzone_name())
    except Exception:
        return "UTC"


def default_user_profile(timezone_name: str | None = None) -> dict[str, Any]:
    return {
        "timezone": timezone_name or _default_timezone(),
        "time_phrase_defaults": {},
        "followup_preference": DEFAULT_FOLLOWUP_PREFERENCE,
        "duration_policy": DEFAULT_DURATION_POLICY,
    }


def normalize_user_profile(
    profile: Mapping[str, Any] | None = None,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    normalized = default_user_profile(timezone_name=timezone_name)
    if profile is None:
        return normalized

    timezone_value = profile.get("timezone")
    if isinstance(timezone_value, str) and timezone_value.strip():
        normalized["timezone"] = timezone_value.strip()

    time_phrase_defaults = profile.get("time_phrase_defaults")
    if isinstance(time_phrase_defaults, Mapping):
        normalized["time_phrase_defaults"] = {
            str(key).strip().lower(): str(value).strip()
            for key, value in time_phrase_defaults.items()
            if str(key).strip() and str(value).strip()
        }

    followup_preference = profile.get("followup_preference")
    if isinstance(followup_preference, str) and followup_preference.strip():
        normalized["followup_preference"] = followup_preference.strip()

    duration_policy = profile.get("duration_policy")
    if isinstance(duration_policy, str) and duration_policy.strip():
        normalized["duration_policy"] = duration_policy.strip()

    return normalized


def ensure_user_profile(
    user_id: str,
    profile: Mapping[str, Any] | None = None,
    timezone_name: str | None = None,
) -> dict[str, Any]:
    existing_profile = load_user_profile(user_id)
    normalized = normalize_user_profile(profile or existing_profile, timezone_name=timezone_name)
    if existing_profile != normalized:
        save_user_profile(user_id, normalized)
    return normalized


def normalize_task_snapshot(task: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if task is None:
        return None
    return {
        "title": task.get("title") or "",
        "description": task.get("description") or "",
        "date": task.get("date"),
        "time": task.get("time"),
        "duration": task.get("duration"),
    }


def validate_error_types(error_types: Iterable[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for error_type in error_types or []:
        if error_type not in ERROR_TYPE_SET:
            raise ValueError(f"Unsupported error type: {error_type}")
        if error_type in seen:
            continue
        seen.add(error_type)
        normalized.append(error_type)
    return normalized


def create_feedback_entry(
    input_text: str,
    parsed_task: Mapping[str, Any],
    user_correct: bool,
    user_id: str,
    error_types: Iterable[str] | None = None,
    corrected_task: Mapping[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "input_text": input_text,
        "parsed_task": normalize_task_snapshot(parsed_task),
        "user_correct": bool(user_correct),
        "error_types": validate_error_types(error_types),
        "corrected_task": normalize_task_snapshot(corrected_task),
        "notes": notes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "user_id": user_id,
    }


def load_feedback_for_user(user_id: str) -> list[dict[str, Any]]:
    return [entry for entry in load_feedback_entries() if entry.get("user_id") == user_id]


def build_feedback_request() -> dict[str, Any]:
    return {
        "question": "Was this correct?",
        "options": ["yes", "no"],
        "negative_path": {
            "question": "What was wrong?",
            "allow_corrections": True,
            "supported_error_types": list(ERROR_TYPES),
        },
    }


def _find_time_phrase(text: str, profile: Mapping[str, Any]) -> str | None:
    lowered_text = text.lower()
    profile_phrases = tuple(profile.get("time_phrase_defaults", {}).keys())
    for phrase in profile_phrases + KNOWN_TIME_PHRASES:
        if phrase and phrase.lower() in lowered_text:
            return phrase.lower()
    return None


def _extract_learning_signals(
    entry: Mapping[str, Any],
    profile: Mapping[str, Any],
) -> list[tuple[str, str, Any]]:
    errors = set(entry.get("error_types") or [])
    parsed_task = entry.get("parsed_task") or {}
    corrected_task = entry.get("corrected_task") or {}
    signals: list[tuple[str, str, Any]] = []

    if "wrong_time" in errors:
        time_phrase = _find_time_phrase(entry.get("input_text", ""), profile)
        corrected_time = corrected_task.get("time")
        if time_phrase and corrected_time:
            signals.append(("time_phrase_defaults", time_phrase, corrected_time))

    if "unnecessary_followup" in errors:
        signals.append(("followup_preference", "followup_preference", "avoid_optional_followups"))

    if "missing_followup" in errors:
        signals.append(("followup_preference", "followup_preference", DEFAULT_FOLLOWUP_PREFERENCE))

    if (
        "wrong_duration" in errors
        and parsed_task.get("duration") is not None
        and corrected_task.get("duration") is None
    ):
        signals.append(("duration_policy", "duration_policy", DEFAULT_DURATION_POLICY))

    return signals


def _build_system_rules(error_counts: Counter[str]) -> list[str]:
    rules: list[str] = []
    if error_counts["wrong_time"] >= AUTO_APPLY_THRESHOLD:
        rules.append(
            "Be conservative with vague time phrases. Use the user's saved time_phrase_defaults when available, otherwise leave time null."
        )
    if error_counts["wrong_duration"] >= AUTO_APPLY_THRESHOLD:
        rules.append("Do not assume a duration unless the user states it clearly.")
    if error_counts["missing_field_not_detected"] >= AUTO_APPLY_THRESHOLD:
        rules.append("If a required scheduling field is missing or ambiguous, keep it null so the app can follow up.")
    if error_counts["missing_followup"] >= AUTO_APPLY_THRESHOLD:
        rules.append("Prefer follow-up questions over silent guesses when scheduling details are ambiguous.")
    if error_counts["unnecessary_followup"] >= AUTO_APPLY_THRESHOLD:
        rules.append("Avoid follow-up questions when the user's saved profile already resolves the ambiguity.")
    if error_counts["misunderstood_text"] >= AUTO_APPLY_THRESHOLD:
        rules.append("When the wording is ambiguous, preserve the original wording in title/description and leave uncertain fields null.")
    return rules


def derive_learning_state(
    feedback_entries: Iterable[Mapping[str, Any]],
    user_profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    profile = normalize_user_profile(user_profile)
    error_counts: Counter[str] = Counter()
    time_phrase_counts: Counter[tuple[str, str]] = Counter()
    followup_counts: Counter[str] = Counter()
    duration_policy_counts: Counter[str] = Counter()

    for entry in feedback_entries:
        if entry.get("user_correct"):
            continue

        error_counts.update(entry.get("error_types") or [])
        for category, key, value in _extract_learning_signals(entry, profile):
            if category == "time_phrase_defaults":
                time_phrase_counts[(key, value)] += 1
            elif category == "followup_preference":
                followup_counts[str(value)] += 1
            elif category == "duration_policy":
                duration_policy_counts[str(value)] += 1

    suggestions: list[dict[str, Any]] = []
    auto_updates: dict[str, Any] = {"time_phrase_defaults": {}}

    for (phrase, time_value), count in time_phrase_counts.items():
        if count >= AUTO_APPLY_THRESHOLD:
            auto_updates["time_phrase_defaults"][phrase] = time_value
        elif count >= SUGGESTION_THRESHOLD:
            suggestions.append(
                {
                    "field": f"time_phrase_defaults.{phrase}",
                    "value": time_value,
                    "occurrences": count,
                    "reason": f'The user has corrected "{phrase}" to {time_value} multiple times.',
                }
            )

    if followup_counts:
        followup_preference, count = followup_counts.most_common(1)[0]
        if followup_preference != profile["followup_preference"]:
            if count >= AUTO_APPLY_THRESHOLD:
                auto_updates["followup_preference"] = followup_preference
            elif count >= SUGGESTION_THRESHOLD:
                suggestions.append(
                    {
                        "field": "followup_preference",
                        "value": followup_preference,
                        "occurrences": count,
                        "reason": "The user keeps correcting the app's follow-up behavior in the same direction.",
                    }
                )

    if duration_policy_counts:
        duration_policy, count = duration_policy_counts.most_common(1)[0]
        if duration_policy != profile["duration_policy"]:
            if count >= AUTO_APPLY_THRESHOLD:
                auto_updates["duration_policy"] = duration_policy
            elif count >= SUGGESTION_THRESHOLD:
                suggestions.append(
                    {
                        "field": "duration_policy",
                        "value": duration_policy,
                        "occurrences": count,
                        "reason": "The user repeatedly removes assumed durations.",
                    }
                )

    adaptive_rules = _build_system_rules(error_counts)
    if not auto_updates["time_phrase_defaults"]:
        auto_updates.pop("time_phrase_defaults")

    return {
        "error_counts": dict(error_counts),
        "suggested_profile_updates": suggestions,
        "auto_profile_updates": auto_updates,
        "adaptive_rules": adaptive_rules,
    }


def _apply_profile_updates(
    profile: Mapping[str, Any],
    updates: Mapping[str, Any],
) -> dict[str, Any]:
    updated_profile = normalize_user_profile(profile)

    time_phrase_updates = updates.get("time_phrase_defaults")
    if isinstance(time_phrase_updates, Mapping):
        merged_time_phrase_defaults = dict(updated_profile["time_phrase_defaults"])
        for phrase, time_value in time_phrase_updates.items():
            if str(phrase).strip() and str(time_value).strip():
                merged_time_phrase_defaults[str(phrase).strip().lower()] = str(time_value).strip()
        updated_profile["time_phrase_defaults"] = merged_time_phrase_defaults

    followup_preference = updates.get("followup_preference")
    if isinstance(followup_preference, str) and followup_preference.strip():
        updated_profile["followup_preference"] = followup_preference.strip()

    duration_policy = updates.get("duration_policy")
    if isinstance(duration_policy, str) and duration_policy.strip():
        updated_profile["duration_policy"] = duration_policy.strip()

    return updated_profile


def get_adaptive_rules(
    user_id: str,
    profile: Mapping[str, Any] | None = None,
) -> list[str]:
    effective_profile = normalize_user_profile(profile or load_user_profile(user_id))
    feedback_entries = load_feedback_for_user(user_id)
    learning_state = derive_learning_state(feedback_entries, user_profile=effective_profile)
    return learning_state["adaptive_rules"]


def record_feedback(
    input_text: str,
    parsed_task: Mapping[str, Any],
    user_correct: bool,
    user_id: str = "default",
    error_types: Iterable[str] | None = None,
    corrected_task: Mapping[str, Any] | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    profile = ensure_user_profile(user_id)
    feedback_entry = create_feedback_entry(
        input_text=input_text,
        parsed_task=parsed_task,
        user_correct=user_correct,
        user_id=user_id,
        error_types=error_types,
        corrected_task=corrected_task,
        notes=notes,
    )
    append_feedback_entry(feedback_entry)

    feedback_entries = load_feedback_for_user(user_id)
    learning_state = derive_learning_state(feedback_entries, user_profile=profile)
    updated_profile = _apply_profile_updates(profile, learning_state["auto_profile_updates"])
    if updated_profile != profile:
        save_user_profile(user_id, updated_profile)

    return {
        "feedback": feedback_entry,
        "user_profile": updated_profile,
        "applied_profile_updates": learning_state["auto_profile_updates"],
        "suggested_profile_updates": learning_state["suggested_profile_updates"],
        "adaptive_rules": learning_state["adaptive_rules"],
        "error_counts": learning_state["error_counts"],
    }
