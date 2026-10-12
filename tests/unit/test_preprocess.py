"""Unit tests for backend/pipeline/preprocess/preprocess.py"""
import cv2
import numpy as np
import pytest

from backend.pipeline.preprocess import preprocess

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
