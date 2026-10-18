"""Pages group into surveys by page order, with dwelling numbers deciding which main form each coded card belongs to."""
import json
from pathlib import Path

from backend.pipeline.run import Run, step_group

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


PREST = {"starts": {"main"}, "matched": {"coded"}, "key": "number_of_dwelling",  # as migration 010 sets collection 1
         "labels": {"main": "Main page", "coded": "Coded page", "notes": "Notes page", "other": "Unknown"}}


def grouped(folder, stem, pages, rule=PREST):
    """Run step_group with a grouping rule on (file, label, transcript or None) pages."""
    run = Run(folder / f"{stem}.pdf", folder / stem, grouping=rule)
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


def test_the_rule_not_the_page_type_names_decides(tmp_path):
    """Prest's pages with every type renamed and the number in another field group exactly as Prest's do."""
    names = {"main": "form", "coded": "card", "notes": "letter", "blank": "blank"}
    rule = {"starts": {"form"}, "matched": {"card"}, "key": "house_no", "labels": {"form": "Form", "card": "Card"}}
    pages = [(f"216412_{i:05d}.png", label, None if label == "blank" else {"number_of_dwelling": n})
             for i, (label, n) in enumerate(PAGES, start=1)]
    prest = grouped(tmp_path / "prest", "216412", pages)
    renamed = grouped(tmp_path / "renamed", "216412", [(file, names[label], t and {"house_no": t["number_of_dwelling"]})
                                                        for file, label, t in pages], rule)
    assert [p["survey"] for p in renamed.pages] == [p["survey"] for p in prest.pages]
    assert [r["file"] for r in renamed.review] == [r["file"] for r in prest.review]
    assert renamed.review[-1]["reason"] == "1 page(s) before the first Form belong to no survey"


def test_without_a_number_field_pages_follow_the_page_that_starts_their_survey(tmp_path):
    rule = {"starts": {"form"}, "matched": set(), "key": None, "labels": {}}
    run = grouped(tmp_path, "b", [("b_00001.png", "form", {}), ("b_00002.png", "letter", {}), ("b_00003.png", "blank", None),
                                  ("b_00004.png", "form", {}), ("b_00005.png", "form", {})], rule)
    assert [p["survey"] for p in run.pages] == ["b_00001", "b_00001", "b_00001", "b_00004", "b_00005"]
    assert run.review == []


def test_with_no_page_type_that_starts_a_survey_each_page_is_one(tmp_path):
    run = grouped(tmp_path, "b", [("b_00001.png", "form", {}), ("b_00002.png", "blank", None), ("b_00003.png", "letter", {})],
                  {"starts": set(), "matched": set(), "key": None, "labels": {}})
    assert [p["survey"] for p in run.pages] == ["b_00001", None, "b_00003"]


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
