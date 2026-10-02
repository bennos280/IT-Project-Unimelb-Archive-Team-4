"""Crop and straighten survey cards, binarise colour by default.

python pipeline/preprocess.py source --output source-pre

optional enhancements:
--greyscale converts to greyscale; --binarize converts to black and white.
--no-deskew skips residual line-based rotation; --no-crop skips boundary rectification.
--c num (i.e. --c 12) sets the adaptive threshold constant. 

Originals are never overwritten.
"""
 
import argparse
import json
import math
from pathlib import Path
 
import cv2
import numpy as np
 
SUPPORTED = {".png", ".jpg", ".jpeg", ".jfif", ".bmp", ".tif", ".tiff", ".webp"}
 
 
def rectify_page(img):
    """Conservatively detect a paper quadrilateral against a light or dark background.

    Work at reduced resolution; transform the original only when four plausible
    corners and visible background margins support the crop.
    """
    h, w = img.shape[:2]
    scale = min(1.0, 1400.0 / max(h, w))
    small = cv2.resize(img, (round(w * scale), round(h * scale)))
    grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    # Separate the light card from a dark scanner border when present.
    border = np.concatenate([grey[0], grey[-1], grey[:, 0], grey[:, -1]])
    if np.median(border) < 100:
        _, mask = cv2.threshold(grey, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    else:
        mask = np.uint8(grey < 245) * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    area = small.shape[0] * small.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True)[:3]:
        if cv2.contourArea(contour) < 0.60 * area:
            continue
        quad = cv2.approxPolyDP(contour, 0.012 * cv2.arcLength(contour, True), True)
        if len(quad) != 4 or not cv2.isContourConvex(quad):
            continue
        pts = quad.reshape(4, 2).astype(np.float32)
        # Put cyclic contour vertices into top-left, top-right, bottom-right,
        # bottom-left order, retaining distinct corners.
        pts = pts[np.argsort(np.arctan2(pts[:, 1] - pts[:, 1].mean(),
                                       pts[:, 0] - pts[:, 0].mean()))]
        pts = np.roll(pts, -np.argmin(pts.sum(axis=1)), axis=0)
        first, second = pts[1] - pts[0], pts[2] - pts[1]
        if first[0] * second[1] - first[1] * second[0] < 0:
            pts = pts[[0, 3, 2, 1]]
        # Reject the image frame and strongly distorted/nonrectangular shapes.
        margins = np.minimum.reduce([pts[:, 0], pts[:, 1],
                    small.shape[1] - 1 - pts[:, 0], small.shape[0] - 1 - pts[:, 1]])
        if margins.max() < 4:
            continue
        vectors = np.roll(pts, -1, axis=0) - pts
        lengths = np.linalg.norm(vectors, axis=1)
        cosines = np.sum(vectors * np.roll(vectors, 1, axis=0), axis=1) / (lengths * np.roll(lengths, 1))
        if np.max(np.abs(cosines)) > 0.25 or lengths.min() < min(small.shape[:2]) * 0.45:
            continue
        # A small outward expansion protects writing close to the detected edge.
        pts = pts / scale
        center = pts.mean(axis=0)
        pts = center + (pts - center) * 1.004
        tl, tr, br, bl = pts
        width = round(max(np.linalg.norm(tr-tl), np.linalg.norm(br-bl)))
        height = round(max(np.linalg.norm(bl-tl), np.linalg.norm(br-tr)))
        target = np.float32([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]])
        matrix = cv2.getPerspectiveTransform(pts.astype(np.float32), target)
        result = cv2.warpPerspective(img, matrix, (width, height),
                    flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
        return result, {"applied": True, "corners": pts.tolist(), "method": "paper_boundary"}
    return img, {"applied": False, "reason": "No reliable four-corner paper boundary"}

def estimate_boundary_skew(small):
    """Use long, agreeing edges on distinct sides of a scanned card.

    Keep this separate from interior ruling: handwriting often has no long
    straight baselines, while a clipped card can still expose several edges.
    """
    h, w = small.shape
    edges = cv2.Canny(small, 30, 100)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 1800, threshold=60,
        minLineLength=max(30, min(h, w) // 2), maxLineGap=25,
    )
    if lines is None:
        return None
    records = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        dx, dy = x2 - x1, y2 - y1
        angle = (math.degrees(math.atan2(dy, dx)) + 45) % 90 - 45
        if abs(angle) > 7:
            continue
        side = None
        if abs(dx) >= w * 0.4:
            if max(y1, y2) < h * 0.1:
                side = "top"
            elif min(y1, y2) > h * 0.9:
                side = "bottom"
        elif abs(dy) >= h * 0.4:
            if max(x1, x2) < w * 0.1:
                side = "left"
            elif min(x1, x2) > w * 0.9:
                side = "right"
        if side is not None:
            records.append((side, angle, math.hypot(dx, dy)))
    # Duplicate Hough detections of one edge must not create confidence.
    by_side = {}
    for side, angle, length in records:
        if side not in by_side or length > by_side[side][1]:
            by_side[side] = (angle, length)
    if len(by_side) < 2:
        return None
    angles, weights = np.asarray(list(by_side.values())).T
    if np.ptp(angles) > 0.6:
        return None
    angle = float(np.average(angles, weights=weights))
    return angle, {"confident": True, "method": "card_edges",
                   "side_count": len(by_side),
                   "candidate_angle": round(angle, 3)}



def estimate_skew_details(grey):
    """Estimate page skew from long lines with similar angles, ignoring image borders."""

    # Shrink large images to speed up detection.
    scale = min(1.0, 1400.0 / max(grey.shape))
    small = cv2.resize(
        grey,
        (round(grey.shape[1] * scale), round(grey.shape[0] * scale)),
    )
    boundary = estimate_boundary_skew(small)
    if boundary is not None:
        return boundary


    # Improve local contrast and detect edges.
    enhanced = cv2.createCLAHE(
        clipLimit=2.0, tileGridSize=(8, 8)
    ).apply(small)
    edges = cv2.Canny(enhanced, 30, 100)

    # Ignore edges near the image border.
    margin = max(3, round(min(small.shape) * 0.025))
    edges[:margin] = edges[-margin:] = 0
    edges[:, :margin] = edges[:, -margin:] = 0

    # Find long straight lines, allowing small gaps.
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 1800, threshold=60,
        minLineLength=max(50, min(small.shape) // 7),
        maxLineGap=12,
    )
    if lines is None:
        return 0.0, {"confident": False, "reason": "No long lines"}

    angles, weights = [], []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        # Express horizontal and vertical lines as a tilt from -45° to 45°.
        angle = (
            math.degrees(math.atan2(y2 - y1, x2 - x1)) + 45
        ) % 90 - 45

        # Keep small tilts and give longer lines more weight.
        if abs(angle) <= 7:
            angles.append(angle)
            weights.append(math.hypot(x2 - x1, y2 - y1))

    # Require at least three lines before estimating skew.
    if len(angles) < 3:
        return 0.0, {
            "confident": False,
            "reason": "Too few near-axis lines",
        }

    angles, weights = np.asarray(angles), np.asarray(weights)

    # Test angles from -7° to 7° in 0.1° steps.
    # Score each by the total length of lines within 0.3°.
    candidates = np.arange(-7, 7.01, 0.1)
    scores = np.array([
        weights[np.abs(angles - a) <= 0.3].sum()
        for a in candidates
    ])

    # Select the strongest angle group.
    peak = candidates[np.argmax(scores)]
    selected = np.abs(angles - peak) <= 0.3

    # Require three agreeing lines and 55% of the total line length.
    support = float(weights[selected].sum() / weights.sum())
    confident = bool(selected.sum() >= 3 and support >= 0.55)

    # Average the selected angles, giving longer lines more influence.
    angle = float(
        np.average(angles[selected], weights=weights[selected])
    )

    # Return zero when uncertain, but record the candidate for review.
    return (angle if confident else 0.0), {
        "confident": confident,
        "support": round(support, 3),
        "line_count": int(selected.sum()),
        "candidate_angle": round(angle, 3),
    }


def estimate_skew_angle(grey):
    return estimate_skew_details(grey)[0]


def estimate_bg_color(img, strip=15):
    """Estimate the page's background color by sampling a thin strip
    of pixels along all four edges and taking the median.
 
    Used to fill the corners left blank when the image is rotated for
    deskewing, so the fill blends in instead of showing as black/white.
    """
    strip = max(1, min(strip, img.shape[0] // 2, img.shape[1] // 2))
        # Gather pixels from the top, bottom, left, and right edge strips.
 
    edge_px = np.concatenate([
        img[:strip].reshape(-1, 3),
        img[-strip:].reshape(-1, 3),
        img[:, :strip].reshape(-1, 3),
        img[:, -strip:].reshape(-1, 3),
    ])
    return tuple(float(x) for x in np.median(edge_px, axis=0))
 
 
def deskew(img, angle):
    """Rotate on an expanded canvas without cropping away survey content."""
    if abs(angle) < 0.05:
        return img
 
    h, w = img.shape[:2]
    center = (w / 2, h / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos_a, sin_a = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w = math.ceil(h * sin_a + w * cos_a)
    new_h = math.ceil(h * cos_a + w * sin_a)
    matrix[0, 2] += new_w / 2 - center[0]
    matrix[1, 2] += new_h / 2 - center[1]
    rotated = cv2.warpAffine(
        img, matrix, (new_w, new_h), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=estimate_bg_color(img),
    )
 
    return rotated


def binarize(grey, block_frac=0.045, C=20):
    """Apply adaptive thresholding to a greyscale image. 
    block_frac: Size of the nearby area used to judge each pixel.
    C: Higher values remove more noise but may erase faint writing.
    """
    block = max(3, int(min(grey.shape) * block_frac))
    if block % 2 == 0:
        block += 1
    return cv2.adaptiveThreshold(
        grey, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, C,
    )
 
 
def transform_array(img, do_deskew=True, keep_color=True, do_binarize=True, source_label="", adaptive_c=20, crop_page=True):
    """Crop and straighten, then optionally convert to greyscale or binary."""

    original_size = [img.shape[1], img.shape[0]]
    crop_report = {"applied": False, "reason": "Disabled"}
    if crop_page:
        img, crop_report = rectify_page(img)
    angle = 0.0
    skew_report = {"confident": False, "reason": "Disabled"}
    if do_deskew:
         # Detect and correct rotation before any further processing.
        angle, skew_report = estimate_skew_details(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        img = deskew(img, angle)
 
    binarized = bool(do_binarize)
    if do_binarize:
        result = binarize(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY), C=adaptive_c)
    elif not keep_color:
        result = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    else:
        result = img.copy()

    report = {
        "source": source_label,
        "page_crop": crop_report,
        "deskew_detection": skew_report,
        "deskew_angle_degrees": round(angle, 3),
        "binarized": binarized,
    }
    return result, report
 
 
def preprocessed_name(source):
    """Use lossless PNG and include the source extension to avoid name collisions."""
    return f"{source.name}_preprocessed.png"

 
 
def process_image(source, destination, args):
    # Decode from bytes so paths containing non-ASCII characters work too.
    image = cv2.imdecode(np.frombuffer(source.read_bytes(), dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Cannot decode image: {source}")
    if min(image.shape[:2]) < 40:
        raise ValueError(f"Image is too small (minimum 40 x 40): {source}")
    if source.suffix.lower() in {".tif", ".tiff"} and cv2.imcount(str(source)) > 1:
        raise ValueError(f"Split multipage TIFF into separate page images first: {source}")
    result, report = transform_array(
        image, not args.no_deskew, not (args.greyscale or args.binarize),
        args.binarize, str(source), adaptive_c=args.c, crop_page=not args.no_crop,
    )
    ok, encoded = cv2.imencode(destination.suffix.lower(), result)
    if not ok:
        raise ValueError(f"Cannot encode output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Exclusive creation prevents accidental overwriting of previous results.
    with destination.open("xb") as stream:
        stream.write(encoded.tobytes())
    report["output"] = str(destination)
    report["image_id"] = source.name
    report["mode"] = "binary" if args.binarize else "greyscale" if args.greyscale else "color"
    report["deskew_enabled"] = not args.no_deskew
    return report
 
 
def main(argv=None):
    from pipeline.common import settings
    from pipeline.preprocess.options import add_arguments, resolve_options

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="One image or a folder of images")
    parser.add_argument("--output", type=Path, help="Folder to write results into")
    add_arguments(parser)
    args = parser.parse_args(argv)
    try:
        options = resolve_options(args, settings())
    except ValueError as exc:
        parser.error(str(exc))
    vars(args).update(vars(options))

    source = args.input.resolve()
    if not source.exists():
        parser.error(f"Input does not exist: {source}")
 
    if source.is_dir():
        # Find supported images, including those in subfolders.
        images = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED and not p.stem.endswith("_preprocessed"))
        if not images:
            parser.error("No supported image files found.")

        # Reject an output folder nested inside the input folder.
        output_root = args.output.resolve() if args.output else None
        if output_root and (output_root == source or source in output_root.parents):
            parser.error("Output folder must be outside the input folder.")

        # Match each image to its output path, keeping the subfolder structure.
        pairs = []
        for p in images:
            out_dir = (output_root / p.relative_to(source).parent) if output_root else p.parent
            pairs.append((p, out_dir / (p.name if output_root else preprocessed_name(p))))
        report_path = (output_root or source) / "preprocessing_report.json"
    else:
        # Check the single image and choose its output paths.
        if source.suffix.lower() not in SUPPORTED:
            parser.error("Input must be an image file or a folder of images")
        out_dir = args.output.resolve() if args.output else source.parent
        pairs = [(source, out_dir / (source.name if args.output else preprocessed_name(source)))]
        report_path = out_dir / f"{source.stem}_preprocessed.json"


 # Avoid overwriting an existing report.
    if report_path.exists():
        parser.error(f"Report already exists: {report_path}")
 
    reports, errors = [], []
    for index, (original, destination) in enumerate(pairs, 1):
        try:
            report = process_image(original, destination, args)
            reports.append(report)
            print(f"[{index}/{len(pairs)}] {original.name} -> {destination.name}: "
                  f"{report['mode']}, skew {report['deskew_angle_degrees']} degrees")
        except (OSError, ValueError, cv2.error) as exc:
                    # Continue with the remaining images if one fails.
            errors.append({"source": str(original), "error": str(exc)})
            print(f"[{index}/{len(pairs)}] FAILED {original.name}: {exc}")
 # Create the report folder and collect settings and results.

    report_path.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema_version": 1,
        "preprocessing_version": "2.0",
        "input": str(source),
        "settings": {"crop_page": not args.no_crop, "deskew": not args.no_deskew,
                     "color": not (args.greyscale or args.binarize),
                     "grayscale": args.greyscale, "binarize": args.binarize,
                     "adaptive_block_fraction": 0.045, "adaptive_C": args.c},
        "processed": len(reports), "failed": len(errors),
        "pages": reports, "errors": errors,
    }

    # Save a new JSON report without overwriting an existing file.

    with report_path.open("x", encoding="utf-8") as stream:
        json.dump(summary, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(f"Report: {report_path}")

    # Return 1 if any image failed, otherwise 0.

    return 1 if errors else 0
 
 
if __name__ == "__main__":
    raise SystemExit(main())