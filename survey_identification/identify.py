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


def _layout_features(image_path: Path) -> dict[str, float]:
    # 测量页面的印刷版式，只用于内部分类 / Measure the printed layout for internal classification only

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

    for index, is_dark in enumerate(dark):
        if not is_dark:
            continue
        row, column = divmod(index, analysis_width)
        row_counts[row] += 1
        column_counts[column] += 1
        third_counts[min(2, column * 3 // analysis_width)] += 1

    row_fractions = [count / analysis_width for count in row_counts]
    column_fractions = [count / analysis_height for count in column_counts]
    third_ink = [count / (total / 3) for count in third_counts]
    largest_third = max(third_ink, default=0.0)

    return {
        "ink": sum(dark) / total,
        "row_max": max(row_fractions, default=0.0),
        "column_max": max(column_fractions, default=0.0),
        "long_rows": float(sum(value >= 0.30 for value in row_fractions)),
        "long_columns": float(sum(value >= 0.30 for value in column_fractions)),
        "active_rows": sum(value >= 0.015 for value in row_fractions) / analysis_height,
        "column_balance": (
            min(third_ink, default=0.0) / largest_third if largest_third else 0.0
        ),
    }


def _classify_layout(features: dict[str, float]) -> str:
    # 使用已标注样本校准的版式规则区分三种页面 / Classify the three page types with layout rules calibrated on labelled samples
    ink = features["ink"]
    row_max = features["row_max"]
    long_rows = features["long_rows"]
    long_columns = features["long_columns"]
    active_rows = features["active_rows"]
    balance = features["column_balance"]

    # 大多数 Page 1 有连续竖表格线 / Most Page 1 forms contain continuous vertical grid lines
    if long_columns >= 1:
        return "page_1"

    # 极浅页面主要是 Page 2；窄行且分布均衡的例外是 Page 3 / Very faint pages are mainly Page 2; balanced narrow-line pages are Page 3
    if ink <= 0.020:
        if balance <= 0.62:
            return "page_2"
        return "page_3" if row_max <= 0.10 else "page_2"

    # 没有长横线且墨迹集中于局部栏位时通常是 Page 3 / Without long horizontal lines, locally concentrated ink usually indicates Page 3
    if balance <= 0.67:
        return "page_3" if long_rows < 1 else "page_2"

    # 版面覆盖较广的是弱表格 Page 1，其余为多栏 Page 3 / Broad coverage indicates a faint-grid Page 1; otherwise it is Page 3
    return "page_1" if active_rows > 0.54 else "page_3"


def identify_page(image_path: Path) -> dict[str, Any]:
    # 只根据图片内容识别，不使用文件名或顺序 / Identify from image content without using its filename or order

    features = _layout_features(image_path)
    return {
        "path": image_path,
        "page_type": _classify_layout(features),
    }


def create_record_sets(images: Iterable[Path]) -> list[list[Path]]:
    # 遇到 Page 1 时开始新 bundle，顺序只用于确定边界 / Start a bundle at Page 1; order only sets boundaries

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
    # 独立识别 bundle 中的每一页 / Identify every page in a bundle independently

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
    # 子文件夹可以表示一组；平铺图片则由 Page 1 分组 / A subfolder may define a set; Page 1 separates flat images
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