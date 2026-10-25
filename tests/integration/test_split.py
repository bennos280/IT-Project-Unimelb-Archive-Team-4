"""PDF page images are replaced together, only after every page renders; a PDF not on this computer is downloaded
from the archive."""
import pickle
import threading
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from backend.pipeline.run import Run, render, step_split


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


def test_pdf_not_on_this_computer_is_downloaded_from_the_archive_and_kept(tmp_path, archive):
    source = tmp_path / "source.pdf"
    make_pdf(source, 2)
    archive.add("216441", {1: ("11", b"jpeg")}, pdf=("10", source.read_bytes()))
    pdf = tmp_path / "data" / "216441" / "10_bundle.pdf"  # as the archive names it: <file id>_<name>
    output = tmp_path / "output"

    step_split(Run(pdf, output))

    assert pdf.read_bytes() == source.read_bytes()  # kept in DATA, so the next run downloads nothing
    assert archive.requests == ["/nodes/download/216441", "/assets/downloadwiz/10"]
    assert [p.name for p in sorted((output / "pages").iterdir())] == ["10_bundle_00001.png", "10_bundle_00002.png"]
    assert [p.name for p in pdf.parent.iterdir()] == ["10_bundle.pdf"]  # no part-downloads left behind


def test_pdf_the_archive_cannot_send_stops_the_run_and_keeps_nothing(tmp_path, archive):
    archive.add("216441", {}, pdf=("10", b"%PDF-1.5 ..." * 1000))
    archive.cut_short.add("10")
    output = tmp_path / "output"
    for pdf in (tmp_path / "data" / "216441" / "10_bundle.pdf",  # broken off halfway
                tmp_path / "data" / "216499" / "11_bundle.pdf"):  # not on the archive
        with pytest.raises(SystemExit, match=f"bundle {pdf.parent.name}'s PDF isn't on this computer, and the archive couldn't send it"):
            step_split(Run(pdf, output))
    assert list((tmp_path / "data" / "216441").iterdir()) == []  # neither the broken-off PDF nor its part-download
    assert not (output / "pages").exists()


def test_a_long_pdf_is_split_on_every_core_in_page_order(tmp_path):
    source = tmp_path / "survey.pdf"
    make_pdf(source, 40)  # more than one 16-page chunk, so several processes draw it
    run = Run(source, tmp_path / "output")
    step_split(run)

    assert sorted(path.name for path in run.images.iterdir()) == [f"survey_{n:05d}.png" for n in range(1, 41)]
    with pymupdf.open(source) as pdf:  # page 33 drawn alone, the same way
        pdf[32].get_pixmap(dpi=200, alpha=False).save(tmp_path / "page33.png")
    assert (run.images / "survey_00033.png").read_bytes() == (tmp_path / "page33.png").read_bytes()


def test_a_page_that_fails_to_draw_is_named_in_an_error_a_worker_process_can_send_back(tmp_path, monkeypatch):
    source = tmp_path / "survey.pdf"
    make_pdf(source, 3)

    class UnsendableError(Exception):  # like PyMuPDF's own errors, which hold a C object
        def __init__(self):
            super().__init__(threading.Lock())

    def get_pixmap(page, *args, **kwargs):
        raise UnsendableError

    monkeypatch.setattr(pymupdf.Page, "get_pixmap", get_pixmap)
    with pytest.raises(RuntimeError, match=r"^survey\.pdf, page 1: UnsendableError") as error:
        render(source, range(3), tmp_path)
    pickle.loads(pickle.dumps(error.value))  # how a worker process sends its error back
