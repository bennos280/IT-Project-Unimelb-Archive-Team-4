"""Integration tests for backend/pipeline/preprocess/preprocess.py: full pipeline calls, real fixture images, pipeline handoff (no model calls)."""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from backend.pipeline import run
from backend.pipeline.preprocess import preprocess
from backend.pipeline.preprocess.options import add_arguments, resolve_options

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