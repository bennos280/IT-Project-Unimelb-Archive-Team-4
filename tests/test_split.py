"""PDF page images are replaced together, only after every page renders."""
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from pipeline.run import Run, step_split


def make_pdf(path, pages, text="original"):
    with pymupdf.open() as pdf:
        for number in range(pages):
            page = pdf.new_page(width=100, height=100)
            page.insert_text((10, 25), f"{text} {number + 1}")
        pdf.save(path)


def fail_on_second_page(monkeypatch):
    render = pymupdf.Page.get_pixmap

    def get_pixmap(page, *args, **kwargs):
        if page.number == 1:
            raise RuntimeError("render failed")
        return render(page, *args, **kwargs)

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", get_pixmap)


def test_shorter_pdf_replaces_old_page_images(tmp_path):
    source = tmp_path / "survey.pdf"
    output = tmp_path / "output"
    make_pdf(source, 2)
    step_split(Run(source, output))
    first_image = (output / "pages" / "survey_00001.png").read_bytes()

    make_pdf(source, 1, text="replacement")
    run = Run(source, output)
    step_split(run)

    assert run.images == output / "pages"
    assert sorted(path.name for path in run.images.iterdir()) == ["survey_00001.png"]
    assert (run.images / "survey_00001.png").read_bytes() != first_image


def test_failed_rerender_preserves_all_previous_images(tmp_path, monkeypatch):
    source = tmp_path / "survey.pdf"
    output = tmp_path / "output"
    make_pdf(source, 2)
    step_split(Run(source, output))
    before = {path.name: path.read_bytes() for path in (output / "pages").iterdir()}

    make_pdf(source, 3, text="replacement")
    fail_on_second_page(monkeypatch)
    with pytest.raises(RuntimeError, match="render failed"):
        step_split(Run(source, output))

    after = {path.name: path.read_bytes() for path in (output / "pages").iterdir()}
    assert after == before


def test_failed_first_render_publishes_no_partial_images(tmp_path, monkeypatch):
    source = tmp_path / "survey.pdf"
    output = tmp_path / "output"
    make_pdf(source, 2)
    fail_on_second_page(monkeypatch)

    with pytest.raises(RuntimeError, match="render failed"):
        step_split(Run(source, output))

    assert not (output / "pages").exists()


def test_failed_publication_restores_previous_images(tmp_path, monkeypatch):
    source = tmp_path / "survey.pdf"
    output = tmp_path / "output"
    make_pdf(source, 2)
    step_split(Run(source, output))
    before = {path.name: path.read_bytes() for path in (output / "pages").iterdir()}
    make_pdf(source, 1, text="replacement")
    rename = Path.rename

    def fail_publication(path, destination):
        if (path.parent.name.startswith(".split-") and path.name == "pages"
                and destination == output / "pages"):
            raise OSError("publication failed")
        return rename(path, destination)

    monkeypatch.setattr(Path, "rename", fail_publication)
    with pytest.raises(OSError, match="publication failed"):
        step_split(Run(source, output))

    assert {path.name: path.read_bytes() for path in (output / "pages").iterdir()} == before


def test_failed_publication_and_restore_retains_previous_images(tmp_path, monkeypatch):
    source = tmp_path / "survey.pdf"
    output = tmp_path / "output"
    make_pdf(source, 2)
    step_split(Run(source, output))
    before = {path.name: path.read_bytes() for path in (output / "pages").iterdir()}
    make_pdf(source, 1, text="replacement")
    rename = Path.rename

    def fail_publication_and_restore(path, destination):
        if (path.parent.name.startswith(".split-") and path.name in ("pages", "previous")
                and destination == output / "pages"):
            raise OSError(f"cannot publish {path.name}")
        return rename(path, destination)

    monkeypatch.setattr(Path, "rename", fail_publication_and_restore)
    with pytest.raises(OSError) as failure:
        step_split(Run(source, output))

    retained = list(output.glob(".split-*/previous"))
    assert len(retained) == 1
    assert {path.name: path.read_bytes() for path in retained[0].iterdir()} == before
    assert not (output / "pages").exists()
    assert str(retained[0]) in "\n".join(getattr(failure.value, "__notes__", []))


def test_image_folder_is_used_without_changes(tmp_path):
    source = tmp_path / "input-pages"
    source.mkdir()
    Image.new("RGB", (10, 10), "white").save(source / "scan.png")
    before = {path.name: path.read_bytes() for path in source.iterdir()}
    output = tmp_path / "output"
    run = Run(source, output)

    step_split(run)

    assert {path.name: path.read_bytes() for path in source.iterdir()} == before
    assert not output.exists()
    assert (run.images or run.input) == source
