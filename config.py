import json
import os

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".autocrew")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULTS = {
    "model": "gpt-5.2",
    "system_prompt": "You are AutoCrew, a helpful AI assistant.",
}


def load() -> dict:
    os.makedirs(CONFIG_DIR, exist_ok=True)
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE) as f:
            return {**DEFAULTS, **json.load(f)}
    return dict(DEFAULTS)
