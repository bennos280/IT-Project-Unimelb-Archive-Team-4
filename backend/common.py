"""Shared by the backend: repo root, the data and output folders, page images."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = {".jpg", ".jpeg", ".png"}


def settings() -> dict[str, str]:
    """The folders for the scans and the results, inside the project."""
    return {"DATA": "data", "OUTPUT": "output"}


def find_images(folder: Path) -> list[Path]:
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in IMAGES)
