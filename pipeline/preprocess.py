"""Preprocess page images: deskew, flatten contrast, binarise.

    python pipeline/preprocess.py source --output source-pre

--color keeps colour, --no-binarize keeps greyscale, --no-deskew skips rotation. Originals are never overwritten.
"""
 
import argparse
import json
import math
from pathlib import Path
 
import cv2
import numpy as np
 
SUPPORTED = {".png", ".jpg", ".jpeg", ".jfif", ".bmp", ".tif", ".tiff", ".webp"}
 
 
def estimate_skew_angle(gray):
    """Estimate skew from the card's dominant horizontal and vertical lines."""
 
    # Find edges to run line detection on.
    edges = cv2.Canny(gray, 40, 120)
    min_line = max(50, min(gray.shape) // 12)
    # Detect straight line segments in the edge map.
 
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 720, threshold=120,
        minLineLength=min_line, maxLineGap=15,
    )
    if lines is None:
        return 0.0
 
    angles = []
    weights = []
    for x1, y1, x2, y2 in np.asarray(lines).reshape(-1, 4):
        length = math.hypot(x2 - x1, y2 - y1)
        angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
    # Fold angle into -45..45 so horizontal- and vertical-leaning
    #lines both describe the same page rotation
 
        if -45 <= angle <= 45:
            folded = angle
        elif angle > 45:
            folded = angle - 90
        else:
            folded = angle + 90
        angles.append(folded)
        weights.append(length)
 
    # Weighted median: sort angles, then find the angle at which the
    # cumulative line length crosses half the total length.
    if not angles:
        return 0.0
    order = np.argsort(angles)
    sorted_angles = np.asarray(angles)[order]
    sorted_weights = np.asarray(weights)[order]
    midpoint = sorted_weights.sum() / 2
    index = int(np.searchsorted(np.cumsum(sorted_weights), midpoint))
    return float(sorted_angles[min(index, len(sorted_angles) - 1)])
 
 
def rotated_rect_max_area(w, h, angle_deg):
    """Compute the largest axis-aligned rectangle that fits inside a
    w x h rectangle after it has been rotated by angle_deg.
 
    Used after deskewing: when an image is rotated, its corners get
    filled with background color; this gives the biggest crop box that
    avoids that filled border, so the crop stays free of blank corners.
    Returns (width, height) of that inner rectangle.
    """
 
    angle = math.radians(angle_deg)
    if w <= 0 or h <= 0:
        return 0.0, 0.0
    width_is_longer = w >= h
    side_long, side_short = (w, h) if width_is_longer else (h, w)
    sin_a, cos_a = abs(math.sin(angle)), abs(math.cos(angle))
    if sin_a < 1e-10:
        # No rotation: the full rectangle already fits.
 
        return w, h
    if side_short <= 2 * sin_a * cos_a * side_long or abs(sin_a - cos_a) < 1e-10:
    # Half-constrained case: the short side limits the fit.
 
        x = 0.5 * side_short
        if width_is_longer:
            wr, hr = x / sin_a, x / cos_a
        else:
            wr, hr = x / cos_a, x / sin_a
    else:
        # General case: solve for the largest rectangle geometrically.
 
        cos_2a = cos_a * cos_a - sin_a * sin_a
        wr = (w * cos_a - h * sin_a) / cos_2a
        hr = (h * cos_a - w * sin_a) / cos_2a
    return wr, hr
 
 
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
    """Rotate by the detected angle and crop away rotation-filled corners."""
    if abs(angle) < 0.05:
        return img
 
    h, w = img.shape[:2]
    center = (w / 2, h / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    cos_a, sin_a = abs(matrix[0, 0]), abs(matrix[0, 1])
    new_w = int(h * sin_a + w * cos_a)
    new_h = int(h * cos_a + w * sin_a)
    matrix[0, 2] += new_w / 2 - center[0]
    matrix[1, 2] += new_h / 2 - center[1]
    rotated = cv2.warpAffine(
        img, matrix, (new_w, new_h), flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_CONSTANT, borderValue=estimate_bg_color(img),
    )
 
    crop_w, crop_h = rotated_rect_max_area(w, h, angle)
    crop_w = max(1, min(new_w, int(crop_w)))
    crop_h = max(1, min(new_h, int(crop_h)))
    x0 = (new_w - crop_w) // 2
    y0 = (new_h - crop_h) // 2
    return rotated[y0:y0 + crop_h, x0:x0 + crop_w]
 
 
def enhance_contrast(img, blur_frac=0.06, low_pct=2.0,
                     high_pct=99.5, gamma=0.9):
    """Flatten uneven lighting/shadows and boost contrast on a grayscale
    (or converted-to-grayscale) page, returning an 8-bit grayscale image.
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    # Estimate the local background lighting with a large blur.
    sigma = max(gray.shape) * blur_frac
    bg = cv2.GaussianBlur(gray, (0, 0), sigmaX=sigma)
    bg = np.maximum(bg, 1)
        # Divide by the background to remove shadows/uneven lighting.
    flattened = cv2.divide(gray, bg, scale=255)
    lo, hi = np.percentile(flattened, [low_pct, high_pct])
    if hi - lo < 1.0:
        # Avoid turning nearly blank, uniformly coloured pages black.
        stretched = flattened
    else:
        stretched = np.clip(
            (flattened.astype(np.float32) - lo) * 255.0 / (hi - lo),
            0, 255,
        ).astype(np.uint8)
        # Apply gamma to brighten midtones for easier OCR/reading.
    return (np.power(stretched.astype(np.float32) / 255.0, gamma) * 255).astype(np.uint8)
 
 
def enhance_color(img):
    """Enhance brightness while retaining coloured annotations such as red ink."""
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    lightness, a, b = cv2.split(lab)
    enhanced_lightness = enhance_contrast(cv2.cvtColor(lightness, cv2.COLOR_GRAY2BGR))
    return cv2.cvtColor(cv2.merge((enhanced_lightness, a, b)), cv2.COLOR_LAB2BGR)
 
 
def binarize(gray, block_frac=0.045, C=15):
    """Turn Adaptive-threshold an grayscale page into pure black/white. 
    block_frac: Size of the nearby area used to judge each pixel.
    C: Higher values remove more noise but may erase faint writing.
    """
    block = max(3, int(min(gray.shape) * block_frac))
    if block % 2 == 0:
        block += 1
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, block, C,
    )
 
 
def transform_array(img, do_deskew, keep_color, do_binarize, source_label):
    """Run deskew, then enhance and/or binarize on one page/image already loaded into memory, and build a
    small JSON-serializable report describing what was done.
    """
 
    original_size = [img.shape[1], img.shape[0]]
    angle = 0.0
    if do_deskew:
         # Detect and correct rotation before any further processing.
        angle = estimate_skew_angle(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        img = deskew(img, angle)
 
    binarized = False
    if keep_color:
        # Color mode: brighten/contrast-enhance but keep colored ink.
        result = enhance_color(img)
    else:
        # Grayscale mode: enhance contrast, optionally reduce to pure B/W.
        result = enhance_contrast(img)
        if do_binarize:
            result = binarize(result)
            binarized = True
 
    report = {
        "source": source_label,
        "deskew_angle_degrees": round(angle, 3),
        "original_working_size": original_size,
        "output_size": [result.shape[1], result.shape[0]],
        "binarized": binarized,
    }
    return result, report
 
 
def preprocessed_name(source):
    """Build the output filename <stem>_preprocessed<ext> for a source image."""
    extension = source.suffix.lower()
    if extension == ".jfif":
        extension = ".jpg"
    return f"{source.stem}_preprocessed{extension}"
 
 
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
        image, not args.no_deskew, args.color,
        not args.no_binarize and not args.color, str(source),
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
    report["mode"] = "color" if args.color else "grayscale" if args.no_binarize else "binary"
    report["deskew_enabled"] = not args.no_deskew
    return report
 
 
def main():
    # Read the input path and processing options.
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("input", type=Path, help="One image or a folder of images")
    parser.add_argument("--output", type=Path,
                        help="Folder to write results into (default: next to each source image)")
    parser.add_argument("--no-deskew", action="store_true", help="Skip small-angle rotation correction")
    parser.add_argument("--color", action="store_true", help="Enhance colour; disables binarisation")
    parser.add_argument("--no-binarize", action="store_true", help="Enhance grayscale without binarisation")
    args = parser.parse_args()

 # Get the full input path and check it exists.
    source = args.input.resolve()
    if not source.exists():
        parser.error(f"Input does not exist: {source}")
 
    if source.is_dir():
        # Find supported images, including those in subfolders.
        images = sorted(p for p in source.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED)
        if not images:
            parser.error("No supported image files found.")

        # Reject an output folder nested inside the input folder.
        output_root = args.output.resolve() if args.output else None
        if output_root and source in output_root.parents:
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
        "preprocessing_version": "1.0",
        "input": str(source),
        "settings": {"deskew": not args.no_deskew, "color": args.color,
                     "binarize": not args.no_binarize and not args.color,
                     "adaptive_block_fraction": 0.045, "adaptive_C": 15,
                     "blur_fraction": 0.06, "low_percentile": 2.0,
                     "high_percentile": 99.5, "gamma": 0.9},
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