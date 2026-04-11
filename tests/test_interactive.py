import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from task_handler import apply_follow_up_answer, next_missing_field, parse_task_with_missing_info


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


def parse_manual_value(field: str, raw_value: str):
    if field == "duration":
        return float(raw_value)
    return raw_value


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
        except Exception as exc:
            print(f"Parser error: {exc}")


if __name__ == "__main__":
    run_manual_parser_test()
