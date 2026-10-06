"""Pages group into surveys by page order, with dwelling numbers deciding which main form each coded card belongs to."""
import json
from pathlib import Path

from pipeline.run import Run, step_group

BUNDLES = Path(__file__).parent / "group"  # real bundles: stored transcripts + Ash's hand grouping of their first surveys
BASELINE = 585  # of Ash's 589 surveys grouped exactly as he did; fail below it

PAGES = [  # label, number_of_dwelling as transcribed (None: not read or not on the page)
    ("notes", None),                                                   # before any main form: flagged
    ("coded", "2"), ("main", "02"), ("notes", None), ("blank", None),  # card before its main form
    ("main", "3"), ("notes", None), ("coded", "3."),                   # card after its main form
    ("main", "4"), ("main", None), ("notes", None), ("coded", "4/5"),  # second main sheet
    ("main", "6"), ("blank", None),                                    # its card is misfiled at the end
    ("main", "7"), ("notes", None), ("coded", "7"),
    ("coded", "8"), ("main", None),                                    # main number unread: flagged
    ("main", "24A"), ("coded", "24A"), ("main", "24 b"), ("coded", "24B"),  # flats
    ("main", "2"), ("coded", "2"),                                     # number used earlier: flagged
    ("coded", "6"),
]


def grouped(folder, stem, pages):
    """Run step_group on (file, label, transcript or None) pages."""
    run = Run(folder / f"{stem}.pdf", folder / stem)
    (run.out / "transcribe").mkdir(parents=True)
    for file, label, transcript in pages:
        page = {"file": file, "label": label}
        if transcript is not None:
            page["transcript"] = f"transcribe/{Path(file).stem}.json"
            (run.out / page["transcript"]).write_text(json.dumps(transcript), encoding="utf-8")
        run.pages.append(page)
    step_group(run)
    return run


def test_cards_join_the_main_form_with_their_number(tmp_path):
    run = grouped(tmp_path, "216412", [(f"216412_{i:05d}.png", label, None if label == "blank" else {"number_of_dwelling": n})
                                       for i, (label, n) in enumerate(PAGES, start=1)])

    assert [p["survey"] for p in run.pages] == ([None] + ["216412-2"] * 4 + ["216412-3"] * 3 + ["216412-4"] * 4
                                                + ["216412-6"] * 2 + ["216412-7"] * 3 + ["216412-8"] * 2
                                                + ["216412-24A"] * 2 + ["216412-24B"] * 2 + ["216412_00024"] * 2
                                                + ["216412-6"])
    assert sorted(r["file"] for r in run.review) == ["216412_00001.png", "216412_00019.png", "216412_00024.png"]


def test_real_bundles_group_like_ash(tmp_path):
    right = total = 0
    silent = []
    for path in sorted(BUNDLES.glob("*.json")):
        bundle = json.loads(path.read_text(encoding="utf-8"))
        run = grouped(tmp_path, bundle["pdf"], [(p["file"], p["label"], p.get("transcript")) for p in bundle["pages"]])
        survey = {p["file"]: p["survey"] for p in run.pages}
        flagged = {survey[r["file"]] for r in run.review}
        ash = {k: {survey[f"{bundle['pdf']}_{n:05d}.png"] for n in pages} for k, pages in bundle["ash"].items()}
        for k, ids in ash.items():
            total += 1
            if len(ids) == 1 and None not in ids and not any(ids & other for j, other in ash.items() if j != k):
                right += 1
            elif not ids & flagged:
                silent.append(f"{bundle['bundle']} {k}")
    print(f"{right}/{total} of Ash's surveys grouped as he did")
    assert not silent, f"grouped differently from Ash with no flag for a human: {silent}"
    assert right >= BASELINE
