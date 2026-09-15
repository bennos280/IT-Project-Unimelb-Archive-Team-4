from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageFilter, ImageOps

from schemas import ADDITIONAL_PAGE, SUPPORTED_EXTENSIONS


_NUMBER_RE = re.compile(r"(\d+)(?!.*\d)")


def scan_number(path: Path) -> int | None:
    match = _NUMBER_RE.search(path.stem)
    return int(match.group(1)) if match else None


def natural_sort_key(path: Path) -> tuple[Any, ...]:
    parts = re.split(r"(\d+)", path.name.casefold())
    return tuple(int(part) if part.isdigit() else part for part in parts)


def find_images(folder: Path) -> list[Path]:
    return sorted(
        (
            item
            for item in folder.iterdir()
            if item.is_file() and item.suffix.casefold() in SUPPORTED_EXTENSIONS
        ),
        key=natural_sort_key,
    )


def _regular_dot_chain(centres: list[float]) -> int:
    # Find repeated small marks with a nearly fixed horizontal gap.
    longest = 0
    for expected_gap in range(3, 11):
        current = 1
        for left, right in zip(centres, centres[1:]):
            if abs((right - left) - expected_gap) <= 1:
                current += 1
            else:
                current = 1
            longest = max(longest, current)
    return longest


def _layout_features(image_path: Path) -> dict[str, float]:
    # Measure the printed layout for internal classification only

    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("L")
    width, height = image.size
    aspect_ratio = width / height

    margin_x = max(1, round(width * 0.035))
    margin_y = max(1, round(height * 0.035))
    image = image.crop((margin_x, margin_y, width - margin_x, height - margin_y))
    image = image.resize((600, 400), Image.Resampling.BILINEAR)

    analysis_width, analysis_height = image.size

    # Measure local detail in the central part of the sheet.  This ignores the
    # dark scan border and works on both pale paper and brown card covers.
    detail_margin_x = round(analysis_width * 0.10)
    detail_margin_y = round(analysis_height * 0.10)
    detail_region = image.crop(
        (
            detail_margin_x,
            detail_margin_y,
            analysis_width - detail_margin_x,
            analysis_height - detail_margin_y,
        )
    )
    blurred_region = detail_region.filter(ImageFilter.GaussianBlur(radius=3))
    detail_difference = ImageChops.difference(detail_region, blurred_region)
    detail_histogram = detail_difference.histogram()
    detail_pixels = detail_region.width * detail_region.height
    content_score = sum(detail_histogram[13:]) / detail_pixels

    # Handwriting is darker than its immediate paper background, even when the
    # entire scan is pale.  Measure coherent dark strokes separately from the
    # absolute amount of detail so that a few faint note lines are not mistaken
    # for an empty sheet.
    local_dark = ImageChops.subtract(blurred_region, detail_region)
    local_dark_pixels = list(local_dark.getdata())
    text_row_fractions = []
    for row in range(detail_region.height):
        row_start = row * detail_region.width
        dark_strokes = sum(
            value >= 13
            for value in local_dark_pixels[
                row_start : row_start + detail_region.width
            ]
        )
        text_row_fractions.append(dark_strokes / detail_region.width)

    # Ignore the lowest part when finding the peak: punch holes, scan borders,
    # and show-through from Page 3 dotted leaders occur there most often.
    text_search_rows = text_row_fractions[: round(detail_region.height * 0.75)]
    text_row_peak = max(text_search_rows, default=0.0)
    text_line_rows = sum(value >= 0.04 for value in text_row_fractions)

    pixels = list(image.getdata())
    # A slightly lighter threshold keeps faint printed rules that disappear in
    # low-contrast scans.
    dark = [value < 150 for value in pixels]
    total = analysis_width * analysis_height

    row_counts = [0] * analysis_height
    column_counts = [0] * analysis_width
    third_counts = [0, 0, 0]
    column_streaks = [0] * analysis_width
    longest_vertical_run = 0

    for index, is_dark in enumerate(dark):
        column = index % analysis_width
        if not is_dark:
            column_streaks[column] = 0
            continue
        row, column = divmod(index, analysis_width)
        row_counts[row] += 1
        column_counts[column] += 1
        third_counts[min(2, column * 3 // analysis_width)] += 1
        column_streaks[column] += 1
        longest_vertical_run = max(longest_vertical_run, column_streaks[column])

    row_fractions = [count / analysis_width for count in row_counts]
    column_fractions = [count / analysis_height for count in column_counts]
    third_ink = [count / (total / 3) for count in third_counts]
    largest_third = max(third_ink, default=0.0)

    dot_chains: list[int] = []
    for row in range(analysis_height):
        row_start = row * analysis_width
        small_mark_centres: list[float] = []
        mark_start: int | None = None

        for column in range(analysis_width + 1):
            is_dark = (
                column < analysis_width
                and dark[row_start + column]
            )
            if is_dark and mark_start is None:
                mark_start = column
            elif not is_dark and mark_start is not None:
                mark_width = column - mark_start
                if mark_width <= 4:
                    small_mark_centres.append((mark_start + column - 1) / 2)
                mark_start = None

        dot_chains.append(_regular_dot_chain(small_mark_centres))

    strongest_dot_rows = sorted(dot_chains, reverse=True)[:20]
    dot_pattern_score = (
        sum(strongest_dot_rows) / len(strongest_dot_rows)
        if strongest_dot_rows
        else 0.0
    )

    return {
        "aspect_ratio": aspect_ratio,
        "content_score": content_score,
        "text_row_peak": text_row_peak,
        "text_line_rows": float(text_line_rows),
        "ink": sum(dark) / total,
        "row_max": max(row_fractions, default=0.0),
        "column_max": max(column_fractions, default=0.0),
        "long_rows": float(sum(value >= 0.30 for value in row_fractions)),
        "long_columns": float(sum(value >= 0.30 for value in column_fractions)),
        "vertical_line_run": longest_vertical_run / analysis_height,
        "dot_pattern_score": dot_pattern_score,
        "dot_pattern_peak": float(max(dot_chains, default=0)),
        "strong_dot_rows": float(sum(value >= 10 for value in dot_chains)),
        "active_rows": sum(value >= 0.015 for value in row_fractions) / analysis_height,
        "column_balance": (
            min(third_ink, default=0.0) / largest_third if largest_third else 0.0
        ),
    }


def _classify_layout(features: dict[str, float]) -> str:
    # Use several pieces of template evidence instead of relying on one line.
    aspect_ratio = features["aspect_ratio"]
    content_score = features["content_score"]
    text_row_peak = features["text_row_peak"]
    text_line_rows = features["text_line_rows"]
    active_rows = features["active_rows"]
    column_balance = features["column_balance"]
    vertical_line_run = features["vertical_line_run"]
    row_max = features["row_max"]
    column_max = features["column_max"]
    long_rows = features["long_rows"]
    dot_pattern_score = features["dot_pattern_score"]
    dot_pattern_peak = features["dot_pattern_peak"]
    strong_dot_rows = features["strong_dot_rows"]

    # Area covers are portrait sheets, unlike the landscape survey pages.
    # Their handwritten title does not make them Page 2.
    portrait_cover = aspect_ratio < 0.90
    viewer_framed_cover = (
        content_score < 0.060
        and active_rows >= 0.80
        and column_balance <= 0.20
    )
    viewer_framed_blank = (
        0.90 <= aspect_ratio < 1.45
        and content_score < 0.010
        and text_row_peak < 0.055
        and text_line_rows < 8
    )
    if portrait_cover or viewer_framed_cover or viewer_framed_blank:
        return ADDITIONAL_PAGE

    # Page 1 normally has a long vertical table line.  A scan can break that
    # line, so a slightly shorter run is accepted only when long horizontal
    # rules and strong row/column coverage confirm the printed table grid.
    strong_vertical_line = vertical_line_run >= 0.18
    broken_but_clear_table = (
        vertical_line_run >= 0.13
        and long_rows >= 2
        and row_max >= 0.45
        and column_max >= 0.28
    )
    if strong_vertical_line or broken_but_clear_table:
        return "page_1"

    # Page 3 has repeated dotted leaders.  Keep the original strong test, but
    # also accept a few partly broken dotted rows when their peak chain is
    # still clearly longer than marks normally produced by handwriting.
    strong_dot_pattern = dot_pattern_score >= 12.0
    broken_but_clear_dots = (
        dot_pattern_score >= 8.0
        and dot_pattern_peak >= 15
        and strong_dot_rows >= 3
    )
    if strong_dot_pattern or broken_but_clear_dots:
        return "page_3"

    # A sheet is blank only when all three independent signals are weak:
    # little overall detail, no strong handwriting row, and too few coherent
    # text-like rows.  The conjunction is intentional; faint or short Page 2
    # notes remain Page 2 as soon as any meaningful handwriting is present.
    truly_blank = (
        content_score < 0.010
        and text_row_peak < 0.055
        and text_line_rows < 8
    )
    if truly_blank:
        return ADDITIONAL_PAGE

    # After both printed templates have been ruled out, the page is notes.
    return "page_2"


def _looks_like_faint_showthrough(features: dict[str, float]) -> bool:
    """
    Detect an almost blank sheet where pale reverse-side print shows through.

    This is intentionally a narrow patch. It only fires when the scan contains
    lots of very low-contrast local detail, but almost no genuinely dark ink.
    That pattern is typical of reverse-side show-through and is different from
    even faint front-side handwriting.
    """
    return (
        1.30 <= features["aspect_ratio"] <= 1.80
        and features["content_score"] >= 0.008
        and features["ink"] < 0.0010
        and features["active_rows"] < 0.02
        and features["row_max"] < 0.025
        and features["column_max"] < 0.025
        and features["vertical_line_run"] < 0.03
        and features["dot_pattern_peak"] < 8
    )


def _handwriting_features(image_path: Path, sideways: bool = False) -> dict[str, Any]:
    """Look for stroke groups at higher resolution, independently of page order.

    These are image heuristics, not OCR. Faint reverse-side handwriting can
    resemble front-side ink; this detector does not read the handwriting.
    """
    with Image.open(image_path) as source:
        image = ImageOps.exif_transpose(source).convert("L")
    image.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
    if sideways:
        image = image.transpose(Image.Transpose.ROTATE_90)
    w, h = image.size
    # Keep the top notes: the old detector discarded about 13% at each edge.
    image = image.crop((round(w * .025), round(h * .025),
                        round(w * .975), round(h * .975)))
    w, h = image.size
    scale = max(w, h) / 1600
    background = image.filter(ImageFilter.GaussianBlur(max(2, 5 * scale)))
    residual = ImageChops.subtract(background, image)
    histogram = residual.histogram()
    # Estimate ordinary paper texture; do not amplify the whole scan blindly.
    target = w * h * .80
    running = 0
    noise = 0
    for level, count in enumerate(histogram):
        running += count
        if running >= target:
            noise = level
            break
    threshold = max(7, noise * 3 + 3)
    values = residual.tobytes()
    mask = bytearray(1 if value >= threshold else 0 for value in values)
    components = []
    for seed in range(len(mask)):
        if not mask[seed]:
            continue
        mask[seed] = 0
        stack = [seed]
        x0 = x1 = seed % w
        y0 = y1 = seed // w
        area = strength = core = 0
        while stack:
            index = stack.pop()
            y, x = divmod(index, w)
            area += 1
            strength += values[index]
            core += values[index] >= threshold * 1.6
            x0, x1 = min(x0, x), max(x1, x)
            y0, y1 = min(y0, y), max(y1, y)
            for ny in range(max(0, y - 1), min(h, y + 2)):
                for nx in range(max(0, x - 1), min(w, x + 2)):
                    neighbour = ny * w + nx
                    if mask[neighbour]:
                        mask[neighbour] = 0
                        stack.append(neighbour)
        cw, ch = x1 - x0 + 1, y1 - y0 + 1
        # Remove isolated specks, straight rules, large stains and edge marks.
        if (area < max(4, 6 * scale * scale)
                or ch < max(3, 4 * scale)
                or cw < 2 or ch > h * .12 or cw > w * .40
                or cw / ch > 12 or ch / cw > 10
                or area / (cw * ch) > .80
                or core < max(3, area * .12)
                or x0 == 0 or y0 == 0 or x1 == w - 1 or y1 == h - 1):
            continue
        # Round punch holes near the bottom do not constitute a note.
        if y0 > h * .82 and .5 < cw / ch < 2 and ch > h * .012:
            continue
        components.append((x0, y0, x1, y1, area, strength / area))

    # Nearby components must form a text-like group, not just scattered dirt.
    groups = []
    for component in sorted(components, key=lambda c: c[0]):
        x0, y0, x1, y1, area, strength = component
        chosen = None
        for group in groups:
            gy0, gy1 = group[1], group[3]
            overlap = min(y1, gy1) - max(y0, gy0) + 1
            typical_height = group[7] / group[5]
            component_height = y1 - y0 + 1
            if (overlap >= .45 * min(component_height, typical_height)
                    and .45 <= component_height / typical_height <= 2.2
                    and abs(y1 - group[8] / group[5]) <= typical_height * .65
                    and x0 - group[2] <= max(10, 22 * scale)
                    and max(y1, gy1) - min(y0, gy0) < h * .08):
                chosen = group
                break
        if chosen is None:
            groups.append([x0, y0, x1, y1, area, 1, strength, y1 - y0 + 1, y1, [component]])
        else:
            chosen[1] = min(chosen[1], y0)
            chosen[2] = max(chosen[2], x1)
            chosen[3] = max(chosen[3], y1)
            chosen[4] += area
            chosen[5] += 1
            chosen[6] = max(chosen[6], strength)
            chosen[7] += y1 - y0 + 1
            chosen[8] += y1
            chosen[9].append(component)
    def repeated_dots(group: list[Any]) -> bool:
        marks = sorted(group[9], key=lambda c: c[0])
        if len(marks) < 5:
            return False
        widths = [c[2] - c[0] + 1 for c in marks]
        heights = [c[3] - c[1] + 1 for c in marks]
        centres = [(c[0] + c[2]) / 2 for c in marks]
        gaps = [b - a for a, b in zip(centres, centres[1:])]
        # Real scans have uneven dots and missing dots. Accept gaps of two
        # or three periods instead of requiring every gap to be identical.
        if not gaps or min(gaps) <= 0:
            return False
        period = sorted(gaps)[len(gaps) // 3]
        regular = sum(
            min(abs(gap - period * multiple) for multiple in (1, 2, 3))
            <= period * .22 for gap in gaps)
        small_marks = sum(
            width <= 10 * scale and height <= 10 * scale
            for width, height in zip(widths, heights))
        return regular >= len(gaps) * .75 and small_marks >= len(marks) * .80


    # Require a compact aligned run, not three unrelated dark patches.
    text_groups = [g for g in groups if not repeated_dots(g)
                   # Isolated crease runs at the rim are not writing. Apply
                   # this in either orientation, without cropping top notes.
                   and g[0] < w * .95 and g[2] > w * .05
                   and g[1] < h * .95 and g[3] > h * .05
                   # Fragmented reverse-side print can align like handwriting,
                   # but its remaining fragments are only a few pixels tall.
                   # Require character-sized components, not their combined box.
                   and sorted(c[3] - c[1] + 1 for c in g[9])[g[5] // 2]
                       >= max(5, 8 * scale)
                   and g[2] - g[0] >= max(22, 35 * scale)
                   and g[4] >= max(40, 70 * scale * scale)
                   and .06 <= g[4] / ((g[2] - g[0] + 1) *
                                          (g[3] - g[1] + 1)) <= .65
                   and (g[5] >= 4 or
                        (g[5] >= 1
                         and g[2] - g[0] >= 4 * (g[3] - g[1] + 1)
                         and g[4] >= max(80, 150 * scale * scale)))]
    return {"has_text": bool(text_groups),
            "stroke_groups": len(text_groups),
            "candidate_components": len(components),
            "local_threshold": threshold}


def identify_page(image_path: Path) -> dict[str, Any]:
    # Identify from image content without using its filename or order

    features = _layout_features(image_path)
    page_type = _classify_layout(features)
    # Preserve the existing cover and printed-template decisions. The old
    # viewer_framed_blank test is NOT a cover test: shallow notes can match it.
    is_cover = features["aspect_ratio"] < .90 or (
        features["content_score"] < .060
        and features["active_rows"] >= .80
        and features["column_balance"] <= .20)
    reason = None
    if is_cover:
        page_type = ADDITIONAL_PAGE
        reason = "cover_page"
    elif _looks_like_faint_showthrough(features):
        # Conservative blank-page patch: do not let pale reverse-side print
        # become Page 2 merely because the handwriting detector finds a few
        # text-like fragments.
        page_type = ADDITIONAL_PAGE
        reason = "blank_sheet"
    elif page_type not in ("page_1", "page_3"):
        evidence = _handwriting_features(image_path)
        if not evidence["has_text"]:
            rotated_evidence = _handwriting_features(image_path, sideways=True)
            if rotated_evidence["has_text"]:
                evidence = rotated_evidence
        page_type = "page_2" if evidence["has_text"] else ADDITIONAL_PAGE
        if page_type == ADDITIONAL_PAGE:
            reason = "unclear_page_format" if evidence["candidate_components"] else "blank_sheet"
    return {"path": image_path, "page_type": page_type,
            "classification_reason": reason}



def create_record_sets(images: Iterable[Path]) -> list[list[Path]]:
    # Start a bundle at Page 1; order only sets boundaries

    ordered = sorted(images, key=natural_sort_key)
    groups: list[list[Path]] = []
    current_group: list[Path] = []

    for image in ordered:
        page_type = identify_page(image)["page_type"]

        if page_type == "page_1":
            if current_group:
                groups.append(current_group)
            current_group = [image]
        else:
            current_group.append(image)

    if current_group:
        groups.append(current_group)

    return groups


def _identify_bundle_pages(images: list[Path]) -> list[dict[str, Any]]:
    # Identify every page in a bundle independently

    identified = [identify_page(image) for image in images]
    identified_by_path = {item["path"]: item for item in identified}
    pages: list[dict[str, Any]] = []
    for image in sorted(images, key=natural_sort_key):
        page = {
            "filename": image.name,
            "page_type": identified_by_path[image]["page_type"],
            "source_path": str(image),
            "classification_reason": identified_by_path[image]["classification_reason"],
        }
        pages.append(page)

    return pages


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return cleaned or "survey"


def process_area(folder: Path) -> list[dict[str, Any]]:
    # Each directory is an independent ordered scan stream. Identify once;
    # only Page 1 creates a boundary, including inside nested directories.
    streams = [folder] + sorted(
        (p for p in folder.rglob("*") if p.is_dir()),
        key=lambda p: natural_sort_key(p.relative_to(folder)))
    groups: list[list[dict[str, Any]]] = []
    for stream in streams:
        current: list[dict[str, Any]] = []
        for image in find_images(stream):
            identified = identify_page(image)
            if identified["page_type"] == "page_1" and current:
                groups.append(current)
                current = []
            current.append({"filename": image.name,
                            "source_path": str(image),
                            "page_type": identified["page_type"],
                            "classification_reason": identified["classification_reason"]})
        if current:
            groups.append(current)
    area_id = _safe_id(folder.name)
    return [{"survey_id": f"{area_id}_{index:03d}", "pages": group}
            for index, group in enumerate(groups, start=1)]



def discover_area_folders(input_folder: Path) -> list[Path]:
    if find_images(input_folder):
        return [input_folder]
    return sorted(
        (
            child
            for child in input_folder.iterdir()
            if child.is_dir()
            and (
                find_images(child)
                or any(
                    grandchild.is_dir() and find_images(grandchild)
                    for grandchild in child.iterdir()
                )
            )
        ),
        key=lambda item: item.name.casefold(),
    )


def process_dataset(input_folder: Path) -> dict[str, list[dict[str, Any]]]:
    folders = discover_area_folders(input_folder)

    return {
        "surveys": [survey for folder in folders for survey in process_area(folder)]
    }