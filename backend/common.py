"""Shared by every step: repo root, .env settings, page images."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {".jpg", ".jpeg", ".png"}
KEYS = ("DATA", "OUTPUT", "MODEL", "EFFORT")


def settings() -> dict[str, str]:
    """KEY=VALUE lines from .env; OUTPUT defaults to output, other keys are required."""
    env = ROOT / ".env"
    if not env.exists():
        sys.exit("no .env: copy .env.example to .env")
    found = {"OUTPUT": "output"}
    for line in env.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            found[key.strip()] = value.partition(" #")[0].strip()
    for key in KEYS:
        if not found.get(key):
            sys.exit(f"{key} not set in .env")
    return found


def find_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGES)
