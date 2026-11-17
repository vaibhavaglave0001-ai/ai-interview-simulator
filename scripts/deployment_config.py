"""Load only deployment settings from the gitignored project .env file."""

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KEYS = ("SECRET_KEY", "TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN", "INTERVIEW_SCORING")


def load_settings():
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            name, separator, value = line.partition("=")
            name = name.strip()
            if separator and name in KEYS and not os.environ.get(name):
                os.environ[name] = value.strip().strip("\"'")
    missing = [name for name in KEYS if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing deployment settings: " + ", ".join(missing))
    return {name: os.environ[name] for name in KEYS}
