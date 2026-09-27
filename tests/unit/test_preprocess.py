"""Unit tests for pipeline/preprocess.py"""
import argparse

import cv2
import numpy as np
import pytest
import json

from pipeline import common
from pipeline.preprocess import preprocess
from pipeline.preprocess.options import add_arguments, resolve_options

# Helper: parse test command-line flags and configuration using the real option parser.
def options(*flags, config=None):
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    return resolve_options(parser.parse_args(flags), config or {})

# Check artificial lines tilted by 4 degrees are detected within 1 degree (magnitude only).
def test_estimate_skew_angle_detects_known_tilt():
    image = np.full((300, 400), 255, dtype=np.uint8)

    for y in range(80, 230, 35):
        cv2.line(image, (70, y), (330, y), 0, 3)

    matrix = cv2.getRotationMatrix2D((200, 150), 4.0, 1.0)
    rotated = cv2.warpAffine(
        image,
        matrix,
        (400, 300),
        flags=cv2.INTER_CUBIC,
        borderValue=255,
    )

    angle = preprocess.estimate_skew_angle(rotated)

    assert abs(abs(angle) - 4.0) < 1.0

# Check default settings, configuration values and command-line overrides have the expected priority.
def test_defaults_and_cli_overrides():
    default = options()
    assert default.binarize and not default.no_crop and not default.no_deskew
    config = {'PREPROCESS_C': '30', 'PREPROCESS_BINARIZE': 'false',
              'PREPROCESS_CROP': 'true', 'PREPROCESS_DESKEW': 'true'}
    assert options(config=config).c == 30
    assert not options(config=config).binarize
    override = options('--c', '0', '--binarize', '--no-crop', '--no-deskew', config=config)
    assert override.c == 0
    assert override.binarize and override.no_crop and override.no_deskew


# Check invalid numbers and conflicting colour modes are rejected with command-line error code 2.
@pytest.mark.parametrize('flags', [('--c', '30z'), ('--colour', '--greyscale')])
def test_invalid_cli_options(flags):
    with pytest.raises(SystemExit) as error:
        options(*flags)
    assert error.value.code == 2

# Check three known tilts use card edges, select the correct rotation direction and leave less than 0.25 degrees detected tilt.
@pytest.mark.parametrize("tilt", [-4.0, 1.6, 4.0])
def test_deskew_uses_agreeing_card_edges_and_corrects_direction(tilt):
    image = np.full((600, 900, 3), 255, dtype=np.uint8)
    cv2.rectangle(image, (20, 20), (880, 580), (0, 0, 0), 2)
    matrix = cv2.getRotationMatrix2D((450, 300), tilt, 1.0)
    rotated = cv2.warpAffine(image, matrix, (900, 600), borderValue=(255, 255, 255))
    angle, report = preprocess.estimate_skew_details(cv2.cvtColor(rotated, cv2.COLOR_BGR2GRAY))
    assert report["method"] == "card_edges"
    assert angle == pytest.approx(-tilt, abs=0.25)
    corrected = preprocess.deskew(rotated, angle)
    residual = preprocess.estimate_skew_angle(cv2.cvtColor(corrected, cv2.COLOR_BGR2GRAY))
    assert abs(residual) < 0.25


# Check blank images and a single edge do not provide enough evidence for boundary-based skew detection.
def test_boundary_skew_rejects_blank_and_single_edge():
    image = np.full((600, 900), 255, dtype=np.uint8)
    assert preprocess.estimate_boundary_skew(image) is None
    cv2.line(image, (20, 20), (880, 40), 0, 3)
    assert preprocess.estimate_boundary_skew(image) is None


# Check edges with conflicting angles are rejected instead of producing an unreliable boundary estimate.
def test_boundary_skew_rejects_disagreeing_edges():
    image = np.full((600, 900), 255, dtype=np.uint8)
    cv2.line(image, (20, 20), (880, 40), 0, 3)
    cv2.line(image, (20, 580), (880, 560), 0, 3)
    assert preprocess.estimate_boundary_skew(image) is None


# ---------------------------------------------------------------- testing main()
@pytest.fixture(autouse=True)
def stub_settings(monkeypatch):
    """Give every test in this file an empty .env, so built-in defaults apply.
    """
    monkeypatch.setattr(common, "settings", lambda: {})

def write_png(path, size=(80, 120), colour=250):
    """Helper that create a plain PNG big enough to pass the 40-pixel minimum."""
    path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(path), np.full((size[0], size[1], 3), colour, np.uint8))
    return path

def test_single_image_without_output_writes_beside_the_source(tmp_path):
    """No --output: the result lands next to the original with a _preprocessed name.
    """
    source = write_png(tmp_path / "page.png")
    before = source.read_bytes()

    code = preprocess.main([str(source), "--colour", "--no-crop", "--no-deskew"])

    assert code == 0
    assert (tmp_path / "page.png_preprocessed.png").exists()
    assert source.read_bytes() == before
    report = json.loads((tmp_path / "page_preprocessed.json").read_text(encoding="utf-8"))
    assert report["processed"] == 1 and report["failed"] == 0

def test_single_image_with_output_keeps_the_original_filename(tmp_path):
    """With --output the file keeps its own name, because the folder disambiguates.

    Note: The `_preprocessed` suffix only exists to avoid a collision when results sit
    beside their sources; in a separate output folder it would be noise.
    """
    source = write_png(tmp_path / "page.png")
    out = tmp_path / "results"

    assert preprocess.main([str(source), "--output", str(out), "--colour"]) == 0
    assert (out / "page.png").exists()
    assert not (out / "page.png_preprocessed.png").exists()

def test_report_records_the_settings_that_were_actually_used(tmp_path):
    """The JSON report is the audit trail: it must reflect the flags, not the defaults.
    Here we ask for greyscale with cropping off and check every switch is mirrored.
    """
    source = write_png(tmp_path / "page.png")

    preprocess.main([str(source), "--greyscale", "--no-crop", "--c", "15"])

    report = json.loads((tmp_path / "page_preprocessed.json").read_text(encoding="utf-8"))
    settings = report["settings"]
    assert settings["grayscale"] is True
    assert settings["binarize"] is False
    assert settings["color"] is False
    assert settings["crop_page"] is False
    assert settings["deskew"] is True
    assert settings["adaptive_C"] == 15
    assert report["schema_version"] == 1
    assert report["pages"][0]["mode"] == "greyscale"


@pytest.mark.parametrize("name", ["notes.txt", "scan.pdf", "archive.zip"])
def test_a_non_image_file_is_a_usage_error(tmp_path, name):
    """Only the extensions in SUPPORTED are accepted as a single input.
    """
    path = tmp_path / name
    path.write_bytes(b"not an image")

    with pytest.raises(SystemExit) as exit_info:
        preprocess.main([str(path)])

    assert exit_info.value.code == 2

def test_a_missing_input_path_is_a_usage_error(tmp_path):
    """A path that does not exist fails before any work starts."""
    with pytest.raises(SystemExit) as exit_info:
        preprocess.main([str(tmp_path / "nope.png")])

    assert exit_info.value.code == 2

def test_folder_mode_processes_every_image_including_subfolders(tmp_path):
    """Folder input recurses (rglob) and mirrors the subfolder layout into --output.
    """
    source = tmp_path / "scans"
    write_png(source / "a.png")
    write_png(source / "box2" / "b.png")
    out = tmp_path / "results"

    code = preprocess.main([str(source), "--output", str(out), "--colour", "--no-crop"])

    assert code == 0
    assert (out / "a.png").exists()
    assert (out / "box2" / "b.png").exists()
    report = json.loads((out / "preprocessing_report.json").read_text(encoding="utf-8"))
    assert report["processed"] == 2

def test_folder_mode_ignores_files_it_has_already_produced(tmp_path):
    """Files whose stem ends in "_preprocessed" are skipped.
    """
    source = tmp_path / "scans"
    write_png(source / "a.png")
    write_png(source / "old_preprocessed.png")

    assert preprocess.main([str(source), "--colour", "--no-crop"]) == 0

    report = json.loads((source / "preprocessing_report.json").read_text(encoding="utf-8"))
    assert report["processed"] == 1
    assert report["pages"][0]["image_id"] == "a.png"

def test_folder_mode_ignores_unsupported_file_types(tmp_path):
    """A README or a stray .pdf inside a scan folder is quietly passed over."""
    source = tmp_path / "scans"
    write_png(source / "a.png")
    (source / "README.txt").write_text("notes", encoding="utf-8")
    (source / "contact_sheet.pdf").write_bytes(b"%PDF-1.4")

    assert preprocess.main([str(source), "--colour", "--no-crop"]) == 0

    report = json.loads((source / "preprocessing_report.json").read_text(encoding="utf-8"))
    assert report["processed"] == 1

def test_folder_with_no_supported_images_is_a_usage_error(tmp_path):
    """An empty or image-free folder stops with a message rather than an empty report."""
    source = tmp_path / "scans"
    source.mkdir()
    (source / "README.txt").write_text("nothing here", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        preprocess.main([str(source)])

    assert exit_info.value.code == 2

def test_output_folder_inside_the_input_folder_is_rejected(tmp_path):
    """--output must not be the input folder or nested inside it.
    """
    source = tmp_path / "scans"
    write_png(source / "a.png")

    for bad_output in (source, source / "results"):
        with pytest.raises(SystemExit) as exit_info:
            preprocess.main([str(source), "--output", str(bad_output)])
        assert exit_info.value.code == 2

def test_an_existing_report_stops_the_run_before_any_processing(tmp_path):
    """The command refuses to overwrite a previous report and writes nothing.
    """
    source = write_png(tmp_path / "page.png")
    (tmp_path / "page_preprocessed.json").write_text("{}", encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        preprocess.main([str(source)])

    assert exit_info.value.code == 2
    assert not (tmp_path / "page.png_preprocessed.png").exists()

def test_one_bad_image_does_not_stop_the_others_but_changes_the_exit_code(tmp_path, capsys):
    """A batch keeps going past a failure, records it, and returns 1.(note this might be subject to change check with team!)
    """
    source = tmp_path / "scans"
    write_png(source / "good.png")
    (source / "broken.png").write_bytes(b"not a real png")

    code = preprocess.main([str(source), "--colour", "--no-crop"])

    assert code == 1
    report = json.loads((source / "preprocessing_report.json").read_text(encoding="utf-8"))
    assert report["processed"] == 1 and report["failed"] == 1
    assert "broken.png" in report["errors"][0]["source"]
    assert "Cannot decode" in report["errors"][0]["error"]
    assert (source / "good.png_preprocessed.png").exists()      # the good one still ran
    assert "FAILED broken.png" in capsys.readouterr().out

def test_invalid_config_value_becomes_a_usage_error(tmp_path, monkeypatch):
    """A bad PREPROCESS_* value in .env exits with code 2 instead of a traceback.
        This is if we are using the settings in .env
    """
    monkeypatch.setattr(common, "settings", lambda: {"PREPROCESS_BINARIZE": "maybe"})
    source = write_png(tmp_path / "page.png")

    with pytest.raises(SystemExit) as exit_info:
        preprocess.main([str(source)])

    assert exit_info.value.code == 2

def test_progress_lines_name_each_file_and_its_detected_skew(tmp_path, capsys):
    """Console output shows "[1/2] name -> name: mode, skew X degrees" per image.
    """
    source = tmp_path / "scans"
    write_png(source / "a.png")
    write_png(source / "b.png")

    preprocess.main([str(source), "--binarize", "--no-crop"])

    out = capsys.readouterr().out
    assert "[1/2] a.png" in out and "[2/2] b.png" in out
    assert "binary, skew" in out
    assert "Report:" in out

from pipeline.preprocess.preprocess import (binarize, deskew, estimate_bg_color,
                                            preprocessed_name, process_image,
                                            rectify_page, transform_array)