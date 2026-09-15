"""Every page image in pages/<label>/ must be identified as <label>."""
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE.parents[1] / "survey_identification"))
from identify import identify_page  # noqa: E402

PAGES = sorted((HERE / "pages").glob("*/*.png"))


def label(result):
    """identify_page's answer, in this suite's folder names."""
    kind = {"page_1": "main", "page_2": "notes", "page_3": "coded"}.get(result["page_type"])
    if kind:
        return kind
    return "blank" if result["classification_reason"] in ("blank_sheet", "unclear_page_format") else "other"


@pytest.mark.parametrize("image", PAGES, ids=lambda p: p.stem)
def test_identify_page(image):
    assert label(identify_page(image)) == image.parent.name
