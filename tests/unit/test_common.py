"""Unit tests for pipeline/common.py: reading .env settings and finding page images."""

import pytest

from pipeline import common


def write_env(folder, text):
    """Helper func create a fake .env file inside `folder`"""
    (folder / ".env").write_text(text, encoding="utf-8")

# ---------------------------------------------------------------- settings()
def test_settings_reads_keys_and_defaults_output(tmp_path, monkeypatch):
    """A well-formed .env is parsed into a dict, and OUTPUT falls back to "output".
    """
    write_env(tmp_path, "DATA=data\nMODEL=sonnet\nEFFORT=high\n")
    monkeypatch.setattr(common, "ROOT", tmp_path)

    config = common.settings()

    assert config["DATA"] == "data"
    assert config["MODEL"] == "sonnet"
    assert config["EFFORT"] == "high"
    # OUTPUT was never written to the file, so the built-in default is used.
    assert config["OUTPUT"] == "output"


def test_settings_strips_comments_whitespace_and_bom(tmp_path, monkeypatch):
    """Real .env files contain trailing " # comments", padding and a BOM.
    """
    text = ("\ufeff# leading comment line\n"
            "DATA=  my data   # folder of PDFs\n"
            "   # an indented comment that must be ignored\n"
            "OUTPUT=out\n"
            "MODEL=sonnet\n"
            "EFFORT=high\n"
            "a line with no equals sign\n")
    (tmp_path / ".env").write_text(text, encoding="utf-8")
    monkeypatch.setattr(common, "ROOT", tmp_path)

    config = common.settings()

    assert config["DATA"] == "my data"      # padding gone, comment gone, inner space kept
    assert config["OUTPUT"] == "out"        # the file's value wins over the default
    assert "a line with no equals sign" not in config

def test_settings_keeps_hash_when_not_preceded_by_space(tmp_path, monkeypatch):
    """Only " #" starts a comment, so a '#' inside a value survives.
    """
    write_env(tmp_path, "DATA=C:/lmaoloser#2\nMODEL=sonnet\nEFFORT=high\n")
    monkeypatch.setattr(common, "ROOT", tmp_path)

    assert common.settings()["DATA"] == "C:/lmaoloser#2"

def test_settings_exits_when_env_file_is_missing(tmp_path, monkeypatch):
    """No .env at all -> a clear instruction, not a traceback."""
    monkeypatch.setattr(common, "ROOT", tmp_path)   # tmp_path has no .env in it

    with pytest.raises(SystemExit, match="no .env"):
        common.settings()

@pytest.mark.parametrize("missing", ["DATA", "MODEL", "EFFORT"])
def test_settings_exits_when_a_required_key_is_missing(tmp_path, monkeypatch, missing):
    """Each required key is individually required.
    """
    lines = {"DATA": "data", "MODEL": "sonnet", "EFFORT": "high"}
    del lines[missing]
    write_env(tmp_path, "".join(f"{k}={v}\n" for k, v in lines.items()))
    monkeypatch.setattr(common, "ROOT", tmp_path)

    with pytest.raises(SystemExit, match=f"{missing} not set"):
        common.settings()

def test_settings_treats_an_empty_value_as_missing(tmp_path, monkeypatch):
    """`DATA=` (present but blank) must be rejected too.
    """
    write_env(tmp_path, "DATA=\nMODEL=sonnet\nEFFORT=high\n")
    monkeypatch.setattr(common, "ROOT", tmp_path)

    with pytest.raises(SystemExit, match="DATA not set"):
        common.settings()

def test_settings_last_duplicate_key_wins(tmp_path, monkeypatch):
    """A repeated key overwrites the earlier one, which is what a dict does.
    """
    write_env(tmp_path, "DATA=first\nDATA=second\nMODEL=sonnet\nEFFORT=high\n")
    monkeypatch.setattr(common, "ROOT", tmp_path)

    assert common.settings()["DATA"] == "second"


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
