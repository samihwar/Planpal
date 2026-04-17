import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from feedback import ERROR_TYPES
from task_handler import (
    apply_follow_up_answer,
    next_missing_field,
    parse_task_with_missing_info,
    submit_task_feedback,
)


FIELD_FORMATS = {
    "date": "natural language is allowed, for example tmrw or today 8 am",
    "time": "natural language is allowed, for example 8 am or tday 14:30",
    "duration": "hours as a number",
}

FIELD_LABELS = {
    "date": "date",
    "time": "time",
    "duration": "duration (hours)",
}
CORE_TASK_FIELDS = ("title", "description", "date", "time", "duration")
ERROR_TYPE_FIELD_MAP = {
    "wrong_title": ("title",),
    "wrong_date": ("date",),
    "wrong_time": ("time",),
    "wrong_duration": ("duration",),
}


def parse_manual_value(field: str, raw_value: str):
    if field == "duration":
        return float(raw_value)
    return raw_value


def parse_feedback_value(field: str, raw_value: str, current_value):
    if raw_value == "":
        return current_value

    if raw_value.lower() == "null":
        if field in {"date", "time", "duration"}:
            return None
        raise ValueError(f"{field} cannot be set to null.")

    return parse_manual_value(field, raw_value)


def prompt_yes_no(prompt: str) -> bool:
    while True:
        answer = input(prompt).strip().lower()
        if answer in {"y", "yes"}:
            return True
        if answer in {"n", "no"}:
            return False
        print("Please answer yes or no.")


def parse_error_type_selection(raw_value: str) -> list[str]:
    numbered_error_types = {str(index): error_type for index, error_type in enumerate(ERROR_TYPES, start=1)}
    parsed_error_types = []
    invalid_error_types = []

    for item in raw_value.split(","):
        token = item.strip()
        if not token:
            continue

        error_type = numbered_error_types.get(token, token)
        if error_type not in ERROR_TYPES:
            invalid_error_types.append(token)
            continue
        if error_type not in parsed_error_types:
            parsed_error_types.append(error_type)

    if invalid_error_types:
        raise ValueError(f"Unsupported error type selections: {', '.join(invalid_error_types)}")
    if not parsed_error_types:
        raise ValueError("Please enter at least one valid error type.")

    return parsed_error_types


def fields_for_error_types(error_types: list[str]) -> tuple[str, ...]:
    fields = []
    for error_type in error_types:
        for field in ERROR_TYPE_FIELD_MAP.get(error_type, ()):
            if field not in fields:
                fields.append(field)
    return tuple(fields)


def prompt_error_types() -> list[str]:
    print("Supported error types:")
    for index, error_type in enumerate(ERROR_TYPES, start=1):
        print(f"{index}. {error_type}")

    while True:
        raw_value = input("What was wrong? Enter one or more numbers separated by commas: ").strip()
        if not raw_value:
            print("Please enter at least one error type.")
            continue

        try:
            return parse_error_type_selection(raw_value)
        except ValueError as exc:
            print(exc)


def prompt_corrected_task(parsed: dict, fields: tuple[str, ...] = CORE_TASK_FIELDS) -> dict | None:
    print("Enter corrected values. Press Enter to keep the current value.")
    print("Type 'null' to clear date, time, or duration.")

    corrected_task = {field: parsed.get(field) for field in CORE_TASK_FIELDS}
    changed = False
    for field in fields:
        current_value = parsed.get(field)
        while True:
            raw_value = input(f"{field} [{current_value}]: ").strip()
            try:
                updated_value = parse_feedback_value(field, raw_value, current_value)
                corrected_task[field] = updated_value
                if updated_value != current_value:
                    changed = True
                break
            except ValueError as exc:
                print(exc)

    return corrected_task if changed else None


def prompt_task_correction_for_error_types(parsed: dict, error_types: list[str]) -> dict | None:
    specific_fields = fields_for_error_types(error_types)
    if specific_fields:
        field_list = ", ".join(specific_fields)
        print(f"Let's correct just the affected field(s): {field_list}")
        return prompt_corrected_task(parsed, fields=specific_fields)

    if prompt_yes_no("Do you want to correct any task fields? (yes/no): "):
        return prompt_corrected_task(parsed)
    return None


def prompt_for_feedback(sentence: str, parsed: dict) -> None:
    print("\nFeedback:")
    was_correct = prompt_yes_no("Was this correct? (yes/no): ")

    if was_correct:
        feedback_result = submit_task_feedback(
            input_text=sentence,
            parsed_task=parsed,
            user_correct=True,
            user_id=parsed.get("user_id", "default"),
        )
        print("Feedback saved.")
        if feedback_result["feedback_result"]["suggested_profile_updates"]:
            print("Profile suggestions:")
            print(json.dumps(feedback_result["feedback_result"]["suggested_profile_updates"], indent=2))
        return

    error_types = prompt_error_types()
    corrected_task = prompt_task_correction_for_error_types(parsed, error_types)
    notes = input("Notes (optional): ").strip() or None

    feedback_result = submit_task_feedback(
        input_text=sentence,
        parsed_task=parsed,
        user_correct=False,
        user_id=parsed.get("user_id", "default"),
        error_types=error_types,
        corrected_task=corrected_task,
        notes=notes,
    )

    print("Feedback saved.")
    print("Updated task after feedback:")
    print(json.dumps({field: feedback_result.get(field) for field in parsed.keys()}, indent=2))

    if feedback_result["feedback_result"]["applied_profile_updates"]:
        print("Applied profile updates:")
        print(json.dumps(feedback_result["feedback_result"]["applied_profile_updates"], indent=2))

    if feedback_result["feedback_result"]["suggested_profile_updates"]:
        print("Suggested profile updates:")
        print(json.dumps(feedback_result["feedback_result"]["suggested_profile_updates"], indent=2))


def run_manual_parser_test() -> None:
    print("Planpal manual parser test")
    print("Enter a sentence to parse. Press Enter on an empty line to exit.")
    print("Follow-up values should use normalized formats.")
    for field, field_format in FIELD_FORMATS.items():
        print(f"- {field}: {field_format}")

    while True:
        sentence = input("\nSentence: ").strip()
        if not sentence:
            print("Exiting manual parser test.")
            break

        try:
            parsed = parse_task_with_missing_info(sentence)
            while parsed["missing_info"]:
                print("\nMissing info:")
                field = next_missing_field(parsed)
                if field is None:
                    break
                answer = input(f"{FIELD_LABELS.get(field, field)}: ").strip()
                if not answer:
                    print("Please enter a value so I can continue.")
                    continue
                try:
                    value = parse_manual_value(field, answer)
                    parsed = apply_follow_up_answer(parsed, field, value)
                except ValueError as exc:
                    print(exc)
                except Exception as exc:
                    print(f"Could not update {field}: {exc}")
                    continue
            print("Parsed result:")
            print(json.dumps(parsed, indent=2))
            prompt_for_feedback(sentence, parsed)
        except Exception as exc:
            print(f"Parser error: {exc}")


if __name__ == "__main__":
    run_manual_parser_test()
