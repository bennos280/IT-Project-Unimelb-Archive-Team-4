"""Unit tests for pipeline/identify/fingerprint.py"""

import numpy as np
from PIL import Image

from pipeline.identify.fingerprint import SIZE, fingerprint


def test_fingerprint_empty_list(monkeypatch):
    """No fingerprints should return expected result
    """
    calls = []

    def fake_clip(views):
        calls.append(views)
        return np.zeros((5, 3), dtype=np.float32)

    monkeypatch.setattr("pipeline.identify.fingerprint._clip", fake_clip)

    result = fingerprint([])

    assert result.shape == (0, 0)
    assert calls == []


def test_fingerprint_builds_5_correctly_sized_views(tmp_path, monkeypatch):
    img_path = tmp_path / "page.jpg"
    Image.new("RGB", (1000, 800), (200, 100, 50)).save(img_path)

    calls = []

    def fake_clip(views):
        calls.append(views)
        return np.zeros((5, 3), dtype=np.float32)

    monkeypatch.setattr("pipeline.identify.fingerprint._clip", fake_clip)

    fingerprint([img_path])

    views_passed_to_clip = calls[0]

    assert len(views_passed_to_clip) == 5
    assert all(view.size == (SIZE, SIZE) for view in views_passed_to_clip)


def test_fingerprint_crops_correct_quadrants(tmp_path, monkeypatch):
    from pipeline.identify.fingerprint import TILE_RENDER
    w, h = TILE_RENDER
    img = Image.new("RGB", (w, h))
    img.paste(Image.new("RGB", (w // 2, h // 2), (255, 0, 0)), (0, 0))
    img.paste(Image.new("RGB", (w // 2, h // 2), (0, 255, 0)), (w // 2, 0))
    img.paste(Image.new("RGB", (w // 2, h // 2), (0, 0, 255)), (0, h // 2))
    img.paste(Image.new("RGB", (w // 2, h // 2), (255, 255, 0)), (w // 2, h // 2))
    img_path = tmp_path / "quadrants.jpg"
    img.save(img_path)

    calls = []

    def fake_clip(views):
        calls.append(views)
        return np.zeros((5, 3), dtype=np.float32)

    monkeypatch.setattr("pipeline.identify.fingerprint._clip", fake_clip)

    fingerprint([img_path])

    views = calls[0]
    top_left, top_right, bottom_left, bottom_right = views[1], views[2], views[3], views[4]

    assert np.array(top_left).std() < 5
    assert np.array(top_right).std() < 5
    assert np.array(bottom_left).std() < 5
    assert np.array(bottom_right).std() < 5