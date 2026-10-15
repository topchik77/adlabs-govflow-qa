import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[3]
load_dotenv(ROOT / ".env")


def database_url():
    return os.environ["DATABASE_URL"]


def secret(name):
    value = os.environ.get(name, "")
    if len(value) < 32 or value.startswith("GENERATE_"):
        raise RuntimeError(f"Generate {name} using python scripts/configure.py")
    return value
