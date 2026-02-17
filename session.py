import json
import os

SESSION_DIR = os.path.join(os.path.expanduser("~"), ".autocrew", "sessions")
DEFAULT_SESSION = os.path.join(SESSION_DIR, "default.jsonl")


def _path() -> str:
    os.makedirs(SESSION_DIR, exist_ok=True)
    return DEFAULT_SESSION


def load() -> list[dict]:
    path = _path()
    if not os.path.exists(path):
        return []
    turns = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                turns.append(json.loads(line))
    return turns


def append(role: str, content: str) -> None:
    with open(_path(), "a") as f:
        f.write(json.dumps({"role": role, "content": content}) + "\n")


def clear() -> None:
    path = _path()
    if os.path.exists(path):
        os.remove(path)
