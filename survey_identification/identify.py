from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageOps, UnidentifiedImageError

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

    try:
        with Image.open(image_path) as source:
            image = ImageOps.exif_transpose(source).convert("L")
    except (OSError, UnidentifiedImageError) as exc:
        raise ValueError(f"Cannot read image: {image_path.name}") from exc

    width, height = image.size
    if width < 40 or height < 40:
        raise ValueError(f"Image is too small: {image_path.name}")

    margin_x = max(1, round(width * 0.035))
    margin_y = max(1, round(height * 0.035))
    image = image.crop((margin_x, margin_y, width - margin_x, height - margin_y))
    image = image.resize((600, 400), Image.Resampling.BILINEAR)

    analysis_width, analysis_height = image.size
    pixels = list(image.getdata())
    dark = [value < 130 for value in pixels]
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
        "ink": sum(dark) / total,
        "row_max": max(row_fractions, default=0.0),
        "column_max": max(column_fractions, default=0.0),
        "long_rows": float(sum(value >= 0.30 for value in row_fractions)),
        "long_columns": float(sum(value >= 0.30 for value in column_fractions)),
        "vertical_line_run": longest_vertical_run / analysis_height,
        "dot_pattern_score": dot_pattern_score,
        "active_rows": sum(value >= 0.015 for value in row_fractions) / analysis_height,
        "column_balance": (
            min(third_ink, default=0.0) / largest_third if largest_third else 0.0
        ),
    }


def _classify_layout(features: dict[str, float]) -> str:
    # Use strong template evidence before treating the page as free-form notes.
    vertical_line_run = features["vertical_line_run"]
    dot_pattern_score = features["dot_pattern_score"]

    # Page 1 contains a continuous vertical line from the printed table.
    if vertical_line_run >= 0.18:
        return "page_1"

    # Page 3 contains many small marks arranged as regularly spaced dotted leaders.
    if dot_pattern_score >= 12.0:
        return "page_3"

    # Without either fixed printed pattern, the page is treated as handwritten notes.
    return "page_2"


def identify_page(image_path: Path) -> dict[str, Any]:
    # Identify from image content without using its filename or order

    features = _layout_features(image_path)
    return {
        "path": image_path,
        "page_type": _classify_layout(features),
    }


def create_record_sets(images: Iterable[Path]) -> list[list[Path]]:
    # Start a bundle at Page 1; order only sets boundaries

    ordered = sorted(images, key=natural_sort_key)
    groups: list[list[Path]] = []
    current_group: list[Path] = []

    for image in ordered:
        try:
            page_type = identify_page(image)["page_type"]
        except ValueError:
            page_type = ADDITIONAL_PAGE

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

    identified: list[dict[str, Any]] = []
    unreadable: dict[Path, str] = {}

    for image in images:
        try:
            identified.append(identify_page(image))
        except ValueError as exc:
            unreadable[image] = str(exc)

    identified_by_path = {item["path"]: item for item in identified}
    pages: list[dict[str, Any]] = []
    for image in sorted(images, key=natural_sort_key):
        if image in unreadable:
            page_type = ADDITIONAL_PAGE
        else:
            page_type = identified_by_path[image]["page_type"]

        page = {
            "filename": image.name,
            "page_type": page_type,
        }
        pages.append(page)

    return pages


def _safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    return cleaned or "survey"


def process_area(folder: Path) -> list[dict[str, Any]]:
    # A subfolder may define a set; Page 1 separates flat images
    survey_folders = sorted(
        (
            child
            for child in folder.iterdir()
            if child.is_dir() and find_images(child)
        ),
        key=lambda item: item.name.casefold(),
    )
    groups = (
        [find_images(survey_folder) for survey_folder in survey_folders]
        if survey_folders
        else create_record_sets(find_images(folder))
    )
    area_id = _safe_id(folder.name)
    return [
        {
            "survey_id": f"{area_id}_{index:03d}",
            "pages": _identify_bundle_pages(group),
        }
        for index, group in enumerate(groups, start=1)
    ]


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
    if not input_folder.exists() or not input_folder.is_dir():
        raise ValueError(f"Input folder does not exist: {input_folder}")

    folders = discover_area_folders(input_folder)
    if not folders:
        raise ValueError(f"No survey images found in: {input_folder}")

    return {
        "surveys": [survey for folder in folders for survey in process_area(folder)]
    }
