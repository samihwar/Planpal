import json
from pathlib import Path

DATA_FILE = Path(__file__).parent.parent / "data" / "tasks.json"

def load_tasks():
    if not DATA_FILE.exists():
        return []
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_tasks(tasks):
    with open(DATA_FILE, "w") as f:
        json.dump(tasks, f, indent=2)