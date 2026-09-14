##Split a survey PDF into page images sorted by page kind
import json
import sys
from pathlib import Path

from PIL import Image, ImageOps

ROOT = Path(__file__).resolve().parent.parent
SIZE = (600, 400)  # analysis resolution; the thresholds below were set at this size


def features(image_path):
    """Three layout measurements of a page image."""
    with Image.open(image_path) as source:
        page = ImageOps.exif_transpose(source).convert("L")
    w, h = page.size
    page = page.crop((int(w * 0.035), int(h * 0.035), int(w * 0.965), int(h * 0.965))).resize(SIZE)
    W, H = SIZE
    dark = [v < 130 for v in page.tobytes()]

    longest_run, run, dark_per_col = 0, [0] * W, [0] * W
    for i, d in enumerate(dark):
        col = i % W
        run[col] = run[col] + 1 if d else 0
        longest_run = max(longest_run, run[col])
        dark_per_col[col] += d

    def dot_chain(row):
        """Longest chain of small marks in this row with a near-constant gap (dotted leaders)."""
        centres, start, best = [], None, 0
        for x in range(W + 1):
            d = x < W and dark[row * W + x]
            if d and start is None:
                start = x
            elif not d and start is not None:
                if x - start <= 4:
                    centres.append((start + x - 1) / 2)
                start = None
        for gap in range(3, 11):
            n = 1
            for a, b in zip(centres, centres[1:]):
                n = n + 1 if abs(b - a - gap) <= 1 else 1
                best = max(best, n)
        return best

    top = sorted((dot_chain(r) for r in range(H)), reverse=True)[:20]
    return {"vline": longest_run / H,
            "dots": sum(top) / len(top),
            "long_cols": sum(c >= H * 0.30 for c in dark_per_col)}


def identify(image_path):
    f = features(image_path)
    if f["vline"] >= 0.12:
        # main forms have <=2 long columns; other printed forms have more
        return "other" if f["long_cols"] >= 4 else "main"
    if f["dots"] >= 15:
        return "coded"
    return "notes"


def main(args):
    if not args or args[0].startswith("-"):
        sys.exit(__doc__)
    import pypdfium2 as pdfium
    pdf = Path(args[0]).resolve()
    unit = pdf.parent.name if pdf.parent.name.isdigit() else pdf.stem
    out = ROOT / "data" / "pages" / unit
    pages = []
    for i, page in enumerate(pdfium.PdfDocument(str(pdf))):
        image = page.render(scale=1600 / page.get_width()).to_pil().convert("L")
        tmp = out / f"{unit}_p{i:03d}.jpg"
        tmp.parent.mkdir(parents=True, exist_ok=True)
        image.save(tmp, quality=85)
        kind = identify(tmp)
        dest = out / kind / tmp.name
        dest.parent.mkdir(exist_ok=True)
        tmp.replace(dest)
        pages.append({"page": i, "kind": kind, "file": dest.relative_to(out).as_posix()})
        print(f"{dest.relative_to(ROOT)}")
    (out / "pages.json").write_text(json.dumps(pages, indent=2) + "\n", encoding="utf-8")
    counts = {k: sum(p["kind"] == k for p in pages) for k in ("main", "notes", "coded", "other")}
    print(f"{out.relative_to(ROOT) / 'pages.json'}  {len(pages)} pages  {counts}")


if __name__ == "__main__":
    main(sys.argv[1:])
