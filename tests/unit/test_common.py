"""Unit tests for backend/common.py: the fixed data and output folders and finding page images."""

from backend import common


# ---------------------------------------------------------------- settings()
def test_settings_gives_the_fixed_folders():
    assert common.settings() == {"DATA": "data", "OUTPUT": "output"}


def test_settings_ignores_any_env_file(tmp_path, monkeypatch):
    """A stale .env (folders, model, or a mess) changes nothing and never stops the app."""
    (tmp_path / ".env").write_text("DATA=elsewhere\nOUTPUT=out\nMODEL=sonnet\nEFFORT=high\nnot a line\n", encoding="utf-8")
    monkeypatch.setattr(common, "ROOT", tmp_path)

    assert common.settings() == {"DATA": "data", "OUTPUT": "output"}


def test_settings_works_with_no_env_file(tmp_path, monkeypatch):
    monkeypatch.setattr(common, "ROOT", tmp_path)

    assert not (tmp_path / ".env").exists()
    assert common.settings() == {"DATA": "data", "OUTPUT": "output"}


# ---------------------------------------------------------------- find_images()
def test_find_images_returns_only_supported_suffixes_sorted(tmp_path):
    """Only .jpg/.jpeg/.png count, and the order is in scan order
    """
    for name in ["b.png", "a.jpg", "c.jpeg", "notes.txt", "scan.pdf", "thumb.gif"]:
        (tmp_path / name).write_bytes(b"x")

    found = common.find_images(tmp_path)

    assert [p.name for p in found] == ["a.jpg", "b.png", "c.jpeg"]

def test_find_images_is_not_recursive_and_ignores_subfolders(tmp_path):
    """Sub-directories are skipped, even one *named* like an image.
    """
    (tmp_path / "top.png").write_bytes(b"x")
    nested = tmp_path / "sub"
    nested.mkdir()
    (nested / "deep.png").write_bytes(b"x")

    assert [p.name for p in common.find_images(tmp_path)] == ["top.png"]

def test_find_images_returns_empty_list_for_a_folder_with_no_pages(tmp_path):
    """An empty result is a legitimate answer, not an error.
    """
    (tmp_path / "readme.txt").write_text("nothing to see", encoding="utf-8")

    assert common.find_images(tmp_path) == []
