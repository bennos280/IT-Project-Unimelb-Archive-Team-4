"""Integration tests for backend/pipeline/preprocess/preprocess.py on real card images (no model calls)."""
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from backend.pipeline.preprocess import preprocess

# Folder containing the real image fixtures; tmp_path holds generated test outputs.
FIXTURES = Path(__file__).parent / "preprocess"

# The app's settings (preprocess.OPTIONS) with these changed; the image code still takes every mode.
def options(**changes):
    return SimpleNamespace(**{**vars(preprocess.OPTIONS), **changes})


# Run each test using card once per real image; read originals without copying or modifying them.
@pytest.fixture(params=["main.jpg", "coded.jpg", "notes.jpg", "skewed_image_1.jpg", "crop.png"])
def card(request):
    path = FIXTURES / request.param
    image = cv2.imread(str(path))
    assert image is not None, f"Cannot read {path}"
    return path, image



# Check each colour, greyscale and binary option produces the right pixels without changing the source.
@pytest.mark.parametrize('changes,mode', [
    ({'binarize': False}, 'color'),
    ({'binarize': False, 'greyscale': True}, 'greyscale'),
    ({}, 'binary'),
])
def test_output_modes_preserve_original(card, tmp_path, changes, mode):
    source, original = card
    before = source.read_bytes()
    destination = tmp_path / 'result.png'
    report = preprocess.process_image(
        source, destination, options(**changes, no_crop=True, no_deskew=True))
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

# Process the real skewed fixture and check confident detection at 1.57 degrees within 0.3 degrees.
def test_skewed_image_detection(tmp_path):
    source = FIXTURES / "skewed_image_1.jpg"
    destination = tmp_path / "skewed_image_1_preprocessed.png"
    report = preprocess.process_image(
        source, destination, options(no_crop=True, binarize=False),
    )
    assert report["deskew_detection"]["confident"] is True
    assert report["deskew_angle_degrees"] == pytest.approx(1.57, abs=0.3)


def test_crop(tmp_path):
    source = FIXTURES / "crop.png"
    image = cv2.imread(str(source))
    assert image is not None
    destination = tmp_path / "crop.png"
    report = preprocess.process_image(
        source, destination, options(binarize=False, no_deskew=True),
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