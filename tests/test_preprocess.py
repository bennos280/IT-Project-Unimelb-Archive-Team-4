"""Preprocessing options, image outputs, and pipeline handoff (no model calls)."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from pipeline import run
from pipeline.preprocess import preprocess
from pipeline.preprocess.options import add_arguments, resolve_options

# Folder containing the real image fixtures; tmp_path holds generated test outputs.
FIXTURES = Path(__file__).parent / "preprocess"

# Helper: parse test command-line flags and configuration using the real option parser.
def options(*flags, config=None):
    parser = argparse.ArgumentParser()
    add_arguments(parser)
    return resolve_options(parser.parse_args(flags), config or {})


# Run each test using card once per real image; read originals without copying or modifying them.
@pytest.fixture(params=["main.jpg", "coded.jpg", "notes.jpg", "skewed_image_1.jpg", "crop.png"])
def card(request):
    path = FIXTURES / request.param
    image = cv2.imread(str(path))
    assert image is not None, f"Cannot read {path}"
    return path, image



# Check each colour, greyscale and binary option produces the right pixels without changing the source.
@pytest.mark.parametrize('flag,mode', [
    ('--colour', 'color'), ('--color', 'color'),
    ('--no-binarize', 'color'), ('--greyscale', 'greyscale'),
    ('--binarize', 'binary'),
])
def test_output_modes_preserve_original(card, tmp_path, flag, mode):
    source, original = card
    before = source.read_bytes()
    destination = tmp_path / 'result.png'
    report = preprocess.process_image(
        source, destination, options(flag, '--no-crop', '--no-deskew'))
    result = cv2.imread(str(destination), cv2.IMREAD_UNCHANGED)
    assert source.read_bytes() == before
    assert report['mode'] == mode
    assert report['page_crop']['reason'] == 'Disabled'
    assert report['deskew_enabled'] is False
    if mode == 'color':
        np.testing.assert_array_equal(result, original)
    elif mode == 'greyscale':
        np.testing.assert_array_equal(result, cv2.cvtColor(original, cv2.COLOR_BGR2GRAY))
        assert len(np.unique(result)) > 2
    else:
        assert result.ndim == 2
        assert set(np.unique(result)) == {0, 255}

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


# Check processing failure is logged for review, leaves the step incomplete and keeps the original page path.
def test_pipeline_failure_records_review_without_completion(tmp_path):
    source = tmp_path / 'bad.png'
    source.write_bytes(b'invalid')
    state = run.Run(tmp_path, tmp_path / 'output', preprocess_options=options())
    state.pages = [{'file': source.name, 'path': str(source), 'label': 'coded'}]
    with pytest.raises(RuntimeError, match='Preprocessing failed'):
        run.step_preprocess(state)
    assert json.loads((state.out / 'review.json').read_text())[0]['step'] == 'preprocess'
    assert not run.completed(state.out, ['preprocess'])
    assert state.pages[0]['path'] == str(source)

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


# Process the real skewed fixture and check confident detection at 1.57 degrees within 0.3 degrees.
def test_skewed_image_detection(tmp_path):
    source = FIXTURES / "skewed_image_1.jpg"
    destination = tmp_path / "skewed_image_1_preprocessed.png"
    report = preprocess.process_image(
        source, destination, options("--no-crop", "--colour"),
    )
    assert report["deskew_detection"]["confident"] is True
    assert report["deskew_angle_degrees"] == pytest.approx(1.57, abs=0.3)


def test_crop(tmp_path):
    source = FIXTURES / "crop.png"
    image = cv2.imread(str(source))
    assert image is not None
    destination = tmp_path / "crop.png"
    report = preprocess.process_image(
        source, destination, options("--colour", "--no-deskew"),
    )
    assert report["page_crop"]["applied"] is True
    cropped = cv2.imread(str(destination))
    h, w = cropped.shape[:2]
    # Check the independently observed paper size, not merely 'applied'.
    assert 945 <= w <= 965
    assert 585 <= h <= 610
    assert h < image.shape[0] and w < image.shape[1]
    # The detected crop must enclose the entire handwritten content area.
    corners = np.array(report["page_crop"]["corners"], dtype=np.float32)
    for point in [(160, 115), (950, 115), (950, 405), (160, 405)]:
        assert cv2.pointPolygonTest(corners, point, False) >= 0
    # Dark outer scanner pixels should largely disappear after cropping.
    def dark_fraction(img):
        return np.mean(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) < 80)
    assert dark_fraction(cropped) < dark_fraction(image) * 0.5