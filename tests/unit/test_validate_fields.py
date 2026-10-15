"""US6's rules read fields by their template names: a field renamed in a template must fail here, not be skipped quietly."""
import json
from pathlib import Path

from backend.pipeline.validate.validator import CONVENTIONS, find_issues

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "backend" / "pipeline" / "transcribe" / "templates"
OPTIONAL = {"sex", "gender"}  # read off a resident when given; the template has no column for them


class Recording(dict):
    """A reading that notes the path of every field looked up in it."""

    def __init__(self, data, path, seen):
        super().__init__({key: wrap(value, path + (key,), seen) for key, value in data.items()})
        self.path, self.seen = path, seen

    def __getitem__(self, key):
        self.seen.add(self.path + (key,))
        return super().__getitem__(key)


def wrap(value, path, seen):
    if isinstance(value, dict):
        return Recording(value, path, seen)
    if isinstance(value, list):
        return [wrap(item, path + (i,), seen) for i, item in enumerate(value)]
    return value


def filled(template):
    """Every field of a template given a value, so every rule reads its fields."""
    if isinstance(template, dict):
        return {key: filled(value) for key, value in template.items()}
    if isinstance(template, list):
        return [filled(item) for item in template]
    return "1"


def in_template(template, path):
    for part in path:
        if isinstance(part, int):
            template = template[0]
        elif isinstance(template, dict) and part in template:
            template = template[part]
        else:
            return False
    return True


def test_every_field_the_rules_read_is_in_the_templates():
    main, coded = (json.loads((TEMPLATES / f"{kind}.json").read_text(encoding="utf-8")) for kind in ("main", "coded"))
    reading = filled(main)
    reading["residents"] = [{**filled(main["residents"][0]), "relationship": "Head", "age": "40"},
                            {**filled(main["residents"][0]), "relationship": "Son", "age": "12"}]
    seen = set()
    find_issues({"main": wrap(reading, ("main",), seen), "coded": wrap(filled(coded), ("coded",), seen)}, dict.fromkeys(CONVENTIONS, True))

    read = {path for path in seen if path[-1] not in OPTIONAL}
    assert {path[0] for path in read} == {"main", "coded"}
    assert any(path[:2] == ("main", "residents") for path in read)  # the residents' rules ran
    templates = {"main": main, "coded": coded}
    assert [path for path in sorted(read, key=str) if not in_template(templates[path[0]], path[1:])] == []


def test_every_codebook_field_is_a_coded_template_field():
    coded = json.loads((TEMPLATES / "coded.json").read_text(encoding="utf-8"))
    codebook = json.loads((ROOT / "backend" / "db" / "data_dict.json").read_text(encoding="utf-8"))["pages"]["3"]["fields"]
    assert sorted(set(codebook) - set(coded)) == []
