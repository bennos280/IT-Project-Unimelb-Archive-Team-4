##Every sample page in source/<kind>/ must be identified as its folder
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from identify import ROOT, identify  # noqa: E402

wrong = []
pages = sorted((ROOT / "source").glob("*/*.jpg"))
for page in pages:
    got = identify(page)
    if got != page.parent.name:
        wrong.append(f"{page.relative_to(ROOT)} -> {got}")
print("\n".join(wrong) or f"{len(pages)} pages identified correctly")
sys.exit(bool(wrong))
