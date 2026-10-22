"""Each series' transcription prompt and each page type's template, saved as versions in the db (jobs use the newest), and the
checks a new version must pass so it can't break loading, grouping or the review screen."""
import hashlib
import json
import re
import subprocess

from backend.db import models
from backend.db.loader import META

PROMPT = "prompt"
KEY = re.compile(r"[a-z][a-z0-9_]*")  #field ids join keys with "." and labels split them at "_"
MAX_CHARS = 32_000  #the prompt, template and schema go on one command line; Windows allows 32,767
SHAPES = {"annotations": [{"raw": None, "location": None, "area": None}],  #the loader stores these as their own tables
          "other_children": {"died": [], "living_elsewhere": []}}


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


#kind -> its newest version: each page type's template, and with a series, its prompt as "prompt" (another series' prompts are left out)
def newest(db, collection_id=None):
    versions = db.query(models.InstructionVersion).order_by(models.InstructionVersion.version_id)
    return {v.kind: v for v in versions if v.kind != PROMPT or (collection_id is not None and v.collection_id == collection_id)}


#kind -> the text a job of this series uses: its prompt (none if it has none) and its page types' templates; None without any
#versions in the db (the pipeline then reads the files)
def texts(db, collection_id):
    if not db.query(models.InstructionVersion).first():
        return None
    types = {name for (name,) in db.query(models.PageType.name).filter_by(collection_id=collection_id)}
    return {kind: v.body for kind, v in newest(db, collection_id).items() if kind == PROMPT or kind in types}


#a series' prompt versions, newest first
def prompt_versions(db, collection_id):
    return (db.query(models.InstructionVersion).filter_by(kind=PROMPT, collection_id=collection_id)
            .order_by(models.InstructionVersion.version_id.desc()).all())


#a new series' first prompt: the general one, which asks nothing of any particular page type
def add_starter_prompt(db, collection_id):
    from backend.pipeline.transcribe.transcribe import read_starter_prompt
    body = read_starter_prompt()
    db.add(models.InstructionVersion(kind=PROMPT, collection_id=collection_id, body=body, sha256=sha256(body), note="Starting prompt"))


#why body can't be saved as kind's newest version; [] if it can. required: page type -> the fields grouping reads (grouping.required_fields)
def problems(kind, body, current, required=None):
    from backend.pipeline.transcribe.transcribe import claude_args, full_prompt
    texts = {**current, kind: body}
    if not texts.get(PROMPT, "").strip():
        return ["The prompt is empty."]
    found = []
    for name in [kind] if kind != PROMPT else [k for k in texts if k != PROMPT]:  #a new prompt changes every template's length
        try:
            template = json.loads(texts[name])
        except ValueError as error:
            found.append(f"{name}: not JSON ({error})")
            continue
        if not isinstance(template, dict):
            found.append(f"{name}: must be a JSON object of fields")
            continue
        found += [f"{name}: {problem}" for problem in template_problems(name, template, (required or {}).get(name))]
        prompt = full_prompt(texts[PROMPT], template)
        line = subprocess.list2cmdline(claude_args("x" * 260, prompt, template, "claude-opus-5-5", "medium"))  #a long image path
        if len(line) > MAX_CHARS:
            found.append(f"{name}: the prompt and template come to {len(line):,} characters on the command line; "
                         f"Windows allows {MAX_CHARS:,}")
    return found


def template_problems(kind, template, required=None):
    found = [] if template else ["needs at least one field"]
    found += [f"'{key}' is filled in by the pipeline" for key in META if key in template]
    found += [f"needs '{key}'" for key in sorted(required or ()) if key not in template]
    for key, value in template.items():
        if key in SHAPES:
            if value != SHAPES[key]:
                found.append(f"'{key}' must be {json.dumps(SHAPES[key])}")
        elif key == "residents":
            if not (isinstance(value, list) and len(value) == 1 and isinstance(value[0], dict) and value[0]
                    and all(v is None for v in value[0].values())):
                found.append("'residents' must be a list holding one object of null fields")
            else:
                found += field_problems("residents", value[0])
        else:
            found += field_problems(None, {key: value})
    return found


#a field is null, its description (text the model reads), or an object of fields; names are lower case
def field_problems(parent, fields):
    found = []
    for key, value in fields.items():
        name = f"{parent}.{key}" if parent else key
        if not KEY.fullmatch(key):
            found.append(f"'{name}': names are lower-case letters, digits and _, starting with a letter")
        if isinstance(value, dict):
            found += field_problems(name, value)
        elif value is not None and not isinstance(value, str):
            found.append(f"'{name}' must be null, its description, or an object of fields")
    return found
