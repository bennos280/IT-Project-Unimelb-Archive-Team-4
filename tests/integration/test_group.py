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


PREST = {"levels": [{"name": "survey", "starts": ["main"], "matched": ["coded"], "key": "number_of_dwelling",  # as migration 023 sets collection 1
                     "parts": [{"type": "main", "count": "one_or_more", "how": "starts"}, {"type": "notes", "count": "any", "how": "follows"},
                               {"type": "coded", "count": "one", "how": "matched"}]}],
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
    rule = {"levels": [{"name": "return", "starts": ["form"], "matched": ["card"], "key": "house_no"}], "labels": {"form": "Form", "card": "Card"}}
    pages = [(f"216412_{i:05d}.png", label, None if label == "blank" else {"number_of_dwelling": n})
             for i, (label, n) in enumerate(PAGES, start=1)]
    prest = grouped(tmp_path / "prest", "216412", pages)
    renamed = grouped(tmp_path / "renamed", "216412", [(file, names[label], t and {"house_no": t["number_of_dwelling"]})
                                                        for file, label, t in pages], rule)
    assert [p["survey"] for p in renamed.pages] == [p["survey"] for p in prest.pages]
    assert [r["file"] for r in renamed.review] == [r["file"] for r in prest.review]
    assert renamed.review[-1]["reason"] == "1 page(s) before the first Form belong to no return"


def test_without_a_number_field_pages_follow_the_page_that_starts_their_survey(tmp_path):
    rule = {"levels": [{"starts": ["form"]}]}
    run = grouped(tmp_path, "b", [("b_00001.png", "form", {}), ("b_00002.png", "letter", {}), ("b_00003.png", "blank", None),
                                  ("b_00004.png", "form", {}), ("b_00005.png", "form", {})], rule)
    assert [p["survey"] for p in run.pages] == ["b_00001", "b_00001", "b_00001", "b_00004", "b_00005"]
    assert run.review == []


def test_with_no_page_type_that_starts_a_survey_each_page_is_one(tmp_path):
    run = grouped(tmp_path, "b", [("b_00001.png", "form", {}), ("b_00002.png", "blank", None), ("b_00003.png", "letter", {})],
                  {"levels": [{}]})
    assert [p["survey"] for p in run.pages] == ["b_00001", None, "b_00003"]


def test_where_each_item_is_one_record_its_pages_are_one_whatever_their_types(tmp_path):
    rule = {**PREST, "levels": []}
    run = grouped(tmp_path, "b", [("b_00001.png", "notes", {}), ("b_00002.png", "blank", None), ("b_00003.png", "main", {"number_of_dwelling": "3"}),
                                  ("b_00004.png", "coded", {"number_of_dwelling": "4"})], rule)
    assert [p["survey"] for p in run.pages] == ["b", None, "b", "b"]
    assert (run.records, run.review) == ([{"id": "b", "parent": None}], [])


def test_a_level_groups_the_pages_of_each_record_of_the_level_above(tmp_path):
    """Folders of letters: a folder's pages before its first letter (its cover) stay in it, unflagged."""
    pages = [("b_00001.png", "cover", {}), ("b_00002.png", "index", {}), ("b_00003.png", "first", {"letter_no": "7"}),
             ("b_00004.png", "page", {}), ("b_00005.png", "first", {"letter_no": "8"}), ("b_00006.png", "blank", None),
             ("b_00007.png", "cover", {}), ("b_00008.png", "first", {})]
    folders = {"name": "folder", "starts": ["cover"]}
    run = grouped(tmp_path / "by order", "b", pages, {"levels": [folders, {"name": "letter", "starts": ["first"]}]})
    assert [p["survey"] for p in run.pages] == ["b_00001", "b_00001", "b_00001-n1", "b_00001-n1", "b_00001-n2", "b_00001-n2",
                                                "b_00007", "b_00007-n1"]
    assert run.records == [{"id": "b_00001", "parent": None}, {"id": "b_00001-n1", "parent": "b_00001"},
                           {"id": "b_00001-n2", "parent": "b_00001"}, {"id": "b_00007", "parent": None},
                           {"id": "b_00007-n1", "parent": "b_00007"}]
    assert run.review == []
    numbered = grouped(tmp_path / "by number", "b", pages,
                       {"levels": [folders, {"name": "letter", "starts": ["first"], "key": "letter_no"}]})
    assert [p["survey"] for p in numbered.pages][2:] == ["b_00001-7", "b_00001-7", "b_00001-8", "b_00001-8", "b_00007", "b_00007-n1"]
    assert [(r["reason"], r["field"]) for r in numbered.review] == [("letter b_00007-n1: no 'letter no'", "letter_no")]


def test_a_level_below_sees_its_records_pages_in_scan_order_with_cards_matched_by_number_in_place(tmp_path):
    rule = {"levels": [{"name": "survey", "starts": ["main"], "matched": ["card"], "key": "n"}, {"name": "section", "starts": ["sec"]}]}
    run = grouped(tmp_path, "it", [("it_1.png", "main", {"n": "1"}), ("it_2.png", "card", {"n": "1"}), ("it_3.png", "sec", {}),
                                   ("it_4.png", "sec", {}), ("it_5.png", "main", {"n": "2"}), ("it_6.png", "sec", {})], rule)
    assert [p["survey"] for p in run.pages] == ["it-1", "it-1", "it-1-n1", "it-1-n2", "it-2", "it-2-n1"]


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
