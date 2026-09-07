from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from identify import process_dataset


# Keep default paths relative to the folder containing main.py
PROJECT_DIR = Path(__file__).resolve().parent
INPUT_FOLDERS = [
    PROJECT_DIR / "split_boxhill_00",
    PROJECT_DIR / "split_brighton_01",
]
OUTPUT_DIR = PROJECT_DIR / "output"

# Match the category names used by the later transcription stage
FOLDER_BY_PAGE = {
    "page_1": "main",
    "page_2": "notes",
    "page_3": "coded",
    "additional_page": "additional",
}


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(data, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")


def safe_area_id(folder: Path) -> str:
    # Remove the split-folder prefix for clearer bundle IDs
    area_id = folder.name.casefold()
    if area_id.startswith("split_"):
        area_id = area_id[6:]
    return area_id


def process_area(folder: Path, classified_folder: Path) -> list[dict[str, Any]]:
    # Classify and bundle each area independently
    internal_result = process_dataset(folder)
    source_by_name = {
        image.name: image
        for image in folder.rglob("*")
        if image.is_file()
    }
    area_id = safe_area_id(folder)
    results: list[dict[str, Any]] = []
    bundle_number = 0

    for survey in internal_result["surveys"]:
        starts_with_page_1 = survey["pages"][0]["page_type"] == "page_1"
        if starts_with_page_1:
            bundle_number += 1
        bundle_id = f"{area_id}_bundle_{bundle_number:04d}" if starts_with_page_1 else None
        occurrence_count = {"page_1": 0, "page_2": 0, "page_3": 0}

        for page in survey["pages"]:
            filename = page["filename"]
            predicted_page = page["page_type"]
            is_additional = False
            additional_reason = None

            # Additional is a bundle status and does not replace a known page type
            if not starts_with_page_1:
                is_additional = True
                additional_reason = "before_first_page_1"
            elif predicted_page == "additional_page":
                is_additional = True
                additional_reason = "unclear_page_format"
            else:
                occurrence_count[predicted_page] += 1
                if occurrence_count[predicted_page] > 1:
                    is_additional = True
                    additional_reason = f"repeated_{predicted_page}"

            destination_folder = classified_folder / FOLDER_BY_PAGE[predicted_page]
            destination_folder.mkdir(parents=True, exist_ok=True)
            destination = destination_folder / filename
            shutil.copy2(source_by_name[filename], destination)
            exported_path = destination.relative_to(classified_folder.parent).as_posix()

            item = {
                "image_id": filename,
                "area_id": area_id,
                "predicted_page": predicted_page,
                "bundle_id": bundle_id,
                "is_additional": is_additional,
                "exported_path": exported_path,
            }
            if is_additional:
                item["additional_reason"] = additional_reason
            results.append(item)

    return results


def run(input_folders: list[Path], output_folder: Path) -> Path:
    # Create one JSON file and three classified image folders
    classified_folder = output_folder / "classified"
    if classified_folder.exists():
        shutil.rmtree(classified_folder)
    for folder_name in FOLDER_BY_PAGE.values():
        (classified_folder / folder_name).mkdir(parents=True, exist_ok=True)

    all_images: list[dict[str, Any]] = []
    for folder in input_folders:
        if not folder.exists() or not folder.is_dir():
            raise ValueError(f"Input folder does not exist: {folder}")
        all_images.extend(process_area(folder, classified_folder))

    result = {
        "areas": [safe_area_id(folder) for folder in input_folders],
        "total_images": len(all_images),
        "page_counts": {
            page_type: sum(item["predicted_page"] == page_type for item in all_images)
            for page_type in FOLDER_BY_PAGE
        },
        "additional_count": sum(item["is_additional"] for item in all_images),
        "images": all_images,
    }
    output_path = output_folder / "survey_output.json"
    write_json(output_path, result)
    return output_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Classify and bundle full survey areas.")
    parser.add_argument(
        "--input",
        type=Path,
        nargs="+",
        default=INPUT_FOLDERS,
        help="One or more area folders containing ordered PNG images.",
    )
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    try:
        output_path = run(args.input, args.output)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    print(f"Survey JSON: {output_path.resolve()}")
    print(f"Classified images: {(args.output / 'classified').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
