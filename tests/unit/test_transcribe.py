"""Unit tests for backend/pipeline/transcribe/transcribe.py schema building and provider handling"""

import json
import subprocess
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from backend.db import app_settings
from backend.pipeline.transcribe import transcribe as transcription
from backend.pipeline.transcribe.transcribe import full_prompt, run_claude, run_cli, run_codex, schema_for, transcribe


@pytest.fixture
def prompt_files(tmp_path, monkeypatch):
    """Point the module at a temporary prompt.txt and templates/ folder.

    `transcribe()` reads both from `HERE`. Redirecting it keeps these tests
    independent of the real prompt wording, which is tuned often -- otherwise
    every prompt tweak would break unrelated tests.
    """
    (tmp_path / "templates").mkdir()
    (tmp_path / "prompt.txt").write_text("Read the card.", encoding="utf-8")
    for kind in ("main", "notes", "coded"):
        (tmp_path / "templates" / f"{kind}.json").write_text(
            '{"text": null}', encoding="utf-8")
    monkeypatch.setattr(transcription, "HERE", tmp_path)
    return tmp_path

# ---------------------------------------------------------------- schema_for()
def test_schemafor_turns_a_flat_template_into_an_object_schema():
    """Every template key becomes a required property of type string-or-null.
    """
    schema = schema_for({"address": None, "municipality": None})

    assert schema["type"] == "object"
    assert schema["required"] == ["address", "municipality"]
    assert schema["additionalProperties"] is False      # nothing extra allowed
    assert schema["properties"]["address"] == {"type": ["string", "null"]}

def test_schemafor_preserves_key_order():
    """`required` follows the template's own order, matching the card's layout.
    """
    schema = schema_for({"z_last": None, "a_first": None, "m_middle": None})

    assert schema["required"] == ["z_last", "a_first", "m_middle"]  # no change!

def test_schemafor_handles_lists_by_describing_their_first_item():
    """A list in the template becomes an array whose items match the example element.
    """
    schema = schema_for({"annotations": [{"raw": None, "location": None}]})

    annotations = schema["properties"]["annotations"]
    assert annotations["type"] == "array"
    assert annotations["items"]["required"] == ["raw", "location"]

def test_schemfor_handles_an_empty_list_without_crashing():
    """`[]` has no first element, so the items fall back to string-or-null.
    """
    assert schema_for([]) == {"type": "array", "items": {"type": ["string", "null"]}}

def test_schemafor_recurses_through_nested_structures():
    """Nesting works to any depth, which the real templates rely on."""
    schema = schema_for({"household": {"members": [{"name": None}]}})

    member = schema["properties"]["household"]["properties"]["members"]["items"]
    assert member["properties"]["name"] == {"type": ["string", "null"]}

@pytest.mark.parametrize("value", [None, 5, True])
def test_schemafor_maps_every_scalar_to_string_or_null(value):
    """Whatever placeholder a template uses, the model is asked for text or null.
    """
    assert schema_for(value) == {"type": ["string", "null"]}


def test_a_field_given_as_text_is_described_by_it_in_the_schema_and_the_prompt():
    """A field's description goes to the model, which is told it isn't the answer; a template without any adds nothing."""
    template = {"status": "Stamped or written at the top", "name": None}
    assert schema_for(template)["properties"]["status"] == {"type": ["string", "null"], "description": "Stamped or written at the top"}
    assert full_prompt("Read the card.", template).endswith("answer with what the page shows, not the description.")
    assert full_prompt("Read the card.", {"name": None}) == 'Read the card.\n\n{\n  "name": null\n}'

def test_schema_for_output_is_json_serialisable():
    """The schema is passed to the CLI via `json.dumps`, so it must serialise.
    """
    json.dumps(schema_for({"a": None, "b": [{"c": None}]}))



# ---------------------------------------------------------------- run_cli()
def test_run_cli_turns_a_hang_into_a_readable_exit(monkeypatch):
    """A CLI that never returns exits with a message naming the timeout.
    """
    def hang(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=transcription.TIMEOUT)

    monkeypatch.setattr(subprocess, "run", hang)

    with pytest.raises(SystemExit, match="timed out"):
        run_cli(["claude"], "claude")


def test_run_cli_explains_a_missing_cli_instead_of_crashing(monkeypatch):
    """If the `claude`/`codex` binary is not installed, say so and how to fix it.
    """
    def absent(*args, **kwargs):
        raise FileNotFoundError("claude")

    monkeypatch.setattr(subprocess, "run", absent)

    with pytest.raises(SystemExit, match="CLI not found"):
        run_cli(["claude"], "claude")

def test_run_cli_passes_capture_and_timeout_settings_through(monkeypatch):
    """Output is captured as text with a timeout and replacement-character decoding.
    """
    seen = {}

    def record(command, **kwargs):
        seen.update(kwargs, command=command)
        return SimpleNamespace(stdout="{}", stderr="", returncode=0)

    monkeypatch.setattr(subprocess, "run", record)
    run_cli(["claude", "-p"], "claude", cwd="/tmp")

    assert seen["capture_output"] is True and seen["text"] is True
    assert seen["timeout"] == transcription.TIMEOUT
    assert seen["errors"] == "replace"
    assert seen["cwd"] == "/tmp"        # extra kwargs are forwarded
    assert seen["command"] == ["claude", "-p"]


# ---------------------------------------------------------------- run_claude()
def test_run_claude_returns_the_structured_output(monkeypatch):
    """A successful reply yields its structured answer.
    """
    reply = {"structured_output": {"text": "Smith"}}
    monkeypatch.setattr(transcription, "run_cli",
                        lambda *a, **k: SimpleNamespace(stdout=json.dumps(reply),
                                                        stderr="", returncode=0))

    assert run_claude("page.jpg", "prompt", {"text": None}, "sonnet", "high") == {"text": "Smith"}

def test_run_claude_builds_the_command_with_the_image_path_and_schema(monkeypatch):
    """The image path is embedded in the prompt and the schema is passed as JSON.
    """
    captured = {}

    def fake_run_cli(command, label, **kwargs):
        captured["command"] = command
        return SimpleNamespace(stdout='{"structured_output": {}}', stderr="", returncode=0)

    monkeypatch.setattr(transcription, "run_cli", fake_run_cli)
    run_claude("/scans/page.jpg", "Read the card.", {"text": None}, "opus", "low")

    command = captured["command"]
    assert command[0] == "claude"
    assert "/scans/page.jpg" in command[2]              # the prompt mentions the image
    assert command[command.index("--model") + 1] == "opus"
    assert command[command.index("--effort") + 1] == "low"
    assert command[command.index("--tools") + 1] == "Read"  # and is the only tool
    assert "--strict-mcp-config" in command             # none of the user's MCP servers
    assert "--safe-mode" in command                     # nor their CLAUDE.md, plugins, hooks, skills or memory
    assert json.loads(command[command.index("--json-schema") + 1])["type"] == "object"

def test_run_claude_exits_when_the_reply_is_not_json(monkeypatch):
    """Non-JSON on stdout (a login prompt, a crash dump) exits with the raw text.
    """
    monkeypatch.setattr(transcription, "run_cli",
                        lambda *a, **k: SimpleNamespace(stdout="Please log in first",
                                                        stderr="", returncode=1))

    with pytest.raises(SystemExit, match="gave no JSON back"):
        run_claude("page.jpg", "p", {"text": None}, "sonnet", "high")


@pytest.mark.parametrize("reply", [
    {"is_error": True, "result": "rate limited"},   # the CLI reported a failure
    {"result": "no schema support"},                 # valid JSON, but no structured_output
])
def test_run_claude_exits_when_the_reply_is_an_error_or_incomplete(monkeypatch, reply):
    """Both failure shapes are rejected before anything is written to disk.
    """
    monkeypatch.setattr(transcription, "run_cli",
                        lambda *a, **k: SimpleNamespace(stdout=json.dumps(reply),
                                                        stderr="", returncode=0))

    with pytest.raises(SystemExit, match="claude failed"):
        run_claude("page.jpg", "p", {"text": None}, "sonnet", "high")


# ---------------------------------------------------------------- run_codex()
def test_run_codex_reads_the_answer_from_the_output_file(monkeypatch, tmp_path):
    """codex writes its last message to a file; we read and parse that.
    """
    def fake_run_cli(command, label, **kwargs):
        last = command[command.index("--output-last-message") + 1]
        with open(last, "w", encoding="utf-8") as stream:
            stream.write('{"text": "Jones"}')
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(transcription, "run_cli", fake_run_cli)

    assert run_codex("page.jpg", "prompt", {"text": None}, "gpt-5", "medium") == {"text": "Jones"}


def test_run_codex_extracts_json_surrounded_by_chatter(monkeypatch):
    """Leading or trailing prose around the JSON is trimmed away.

    reason: codex sometimes wraps its answer in "Here is the result: {...} Hope that
    helps." The code slices between the first `{` and the last `}`
    """
    def fake_run_cli(command, label, **kwargs):
        last = command[command.index("--output-last-message") + 1]
        with open(last, "w", encoding="utf-8") as stream:
            stream.write('Here is the result:\n{"text": "Brown"}\nHope that helps.')
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(transcription, "run_cli", fake_run_cli)

    assert run_codex("p.jpg", "prompt", {"text": None}, "gpt-5", "low") == {"text": "Brown"}

def test_run_codex_runs_read_only_and_ephemeral(monkeypatch):
    """The sandbox is read-only and the session is ephemeral.
    """
    captured = {}

    def fake_run_cli(command, label, **kwargs):
        captured["command"] = command
        last = command[command.index("--output-last-message") + 1]
        with open(last, "w", encoding="utf-8") as stream:
            stream.write("{}")
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(transcription, "run_cli", fake_run_cli)
    run_codex("page.jpg", "prompt", {"text": None}, "gpt-5", "high")

    command = captured["command"]
    assert command[:2] == ["codex", "exec"]
    assert "--ephemeral" in command and "--ignore-user-config" in command
    assert command[command.index("--sandbox") + 1] == "read-only"
    assert command[command.index("--image") + 1] == "page.jpg"

@pytest.mark.parametrize("returncode,write_file", [(1, True), (0, False)])
def test_run_codex_exits_on_a_bad_exit_code_or_a_missing_answer_file(monkeypatch,
                                                                     returncode, write_file):
    """Either a non-zero exit or an absent output file is a failure.
    """
    def fake_run_cli(command, label, **kwargs):
        if write_file:
            last = command[command.index("--output-last-message") + 1]
            with open(last, "w", encoding="utf-8") as stream:
                stream.write("{}")
        return SimpleNamespace(stdout="", stderr="boom", returncode=returncode)

    monkeypatch.setattr(transcription, "run_cli", fake_run_cli)

    with pytest.raises(SystemExit, match="codex failed"):
        run_codex("page.jpg", "prompt", {"text": None}, "gpt-5", "high")

def test_run_codex_exits_when_the_answer_file_holds_no_json(monkeypatch):
    """Prose with no braces at all cannot be parsed, and says so."""
    def fake_run_cli(command, label, **kwargs):
        last = command[command.index("--output-last-message") + 1]
        with open(last, "w", encoding="utf-8") as stream:
            stream.write("I could not read the image.")
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(transcription, "run_cli", fake_run_cli)

    with pytest.raises(SystemExit, match="gave no JSON back"):
        run_codex("page.jpg", "prompt", {"text": None}, "gpt-5", "high")


# ---------------------------------------------------------------- transcribe()
@pytest.mark.parametrize("provider,model", [("claude", "sonnet"), ("codex", "o3")])
def test_transcribe_reads_with_the_provider_it_is_given(prompt_files, monkeypatch, provider, model):
    """The provider picks the CLI, whatever the model is called (an OpenAI o3 isn't named gpt-*)."""
    used = []
    for name in ("run_claude", "run_codex"):
        monkeypatch.setattr(transcription, name,
                            lambda *a, _n=name, **k: (used.append(_n) or {"text": "x"}))

    answer = transcribe("page.jpg", "main", provider=provider, model=model, effort="high")

    assert used == [f"run_{provider}"]
    assert answer["provider"] == provider


def test_transcribe_refuses_an_unknown_provider(prompt_files):
    with pytest.raises(SystemExit, match="PROVIDER must be one of claude, codex, anthropic, openai, gemini, openrouter, ollama, not 'chatgpt'"):
        transcribe("page.jpg", "main", provider="chatgpt", model="gpt-5", effort="high")

def test_transcribe_stamps_every_answer_with_provenance(prompt_files, monkeypatch):
    """provider, model, effort and seconds are added to the returned dict.
    """
    monkeypatch.setattr(transcription, "run_claude",
                        lambda *a, **k: {"text": "Smith"})

    answer = transcribe("page.jpg", "main", provider="claude", model="claude-sonnet-4", effort="high")

    assert answer["text"] == "Smith"
    assert answer["provider"] == "claude"
    assert answer["model"] == "claude-sonnet-4"
    assert answer["effort"] == "high"
    assert isinstance(answer["seconds"], float) and answer["seconds"] >= 0

def test_transcribe_unwraps_a_notes_answer_returned_as_a_json_string(prompt_files, monkeypatch):
    """Sometimes a model puts the whole object inside the "text" field as a string. test that code
    fixes it
    """
    nested = json.dumps({"text": "the real note", "page": "3"})
    monkeypatch.setattr(transcription, "run_claude", lambda *a, **k: {"text": nested})

    answer = transcribe("page.jpg", "notes", provider="claude", model="sonnet", effort="high")

    assert answer["text"] == "the real note"
    assert answer["page"] == "3"

@pytest.mark.parametrize("text", [
    "a plain handwritten note",             # ordinary text is left alone
    "{not valid json at all",               # looks like JSON, is not: keep as-is
])
def test_transcribe_leaves_ordinary_text_untouched(prompt_files, monkeypatch, text):
    """
    A note that genuinely begins with "{" must not be mangled or crash the run;
    """
    monkeypatch.setattr(transcription, "run_claude", lambda *a, **k: {"text": text})

    assert transcribe("page.jpg", "notes", provider="claude", model="sonnet", effort="high")["text"] == text

def test_transcribe_sends_the_template_inside_the_prompt(prompt_files, monkeypatch):
    """The prompt is prompt.txt plus the pretty-printed template for that page kind.
    """
    captured = {}

    def fake_run_claude(image, prompt, template, model, effort):
        captured.update(prompt=prompt, template=template)
        return {"text": "x"}

    monkeypatch.setattr(transcription, "run_claude", fake_run_claude)
    transcribe("page.jpg", "coded", provider="claude", model="sonnet", effort="high")

    assert captured["prompt"].startswith("Read the card.")
    assert '"text": null' in captured["prompt"]
    assert captured["template"] == {"text": None}

def test_transcribe_without_a_choice_uses_the_one_saved_on_the_settings_page(prompt_files, cli_db, monkeypatch):
    with cli_db() as db:
        app_settings.save_transcription_defaults(db, "claude", "haiku", "low")
    monkeypatch.setattr(transcription, "run_claude", lambda *a, **k: {"text": "x"})

    answer = transcribe("page.jpg", "main")

    assert (answer["provider"], answer["model"], answer["effort"]) == ("claude", "haiku", "low")


def test_transcribe_with_a_full_choice_needs_nothing_saved(prompt_files, monkeypatch):
    monkeypatch.setattr(app_settings, "saved_choice_or_exit", lambda: pytest.fail("the db was read"))
    monkeypatch.setattr(transcription, "run_claude", lambda *a, **k: {"text": "x"})

    answer = transcribe("page.jpg", "main", provider="claude", model="opus", effort="high")

    assert (answer["provider"], answer["model"], answer["effort"]) == ("claude", "opus", "high")


def test_transcribe_without_a_choice_and_nothing_saved_exits_with_the_message(prompt_files, cli_db, monkeypatch):
    monkeypatch.setattr(transcription, "run_claude", lambda *a, **k: pytest.fail("a model was called"))

    with pytest.raises(SystemExit, match="Choose a transcription model on the Settings page first."):
        transcribe("page.jpg", "main")
    with pytest.raises(SystemExit, match="Choose a transcription model on the Settings page first."):
        transcribe("page.jpg", "main", provider="claude")  # part of a choice still needs the rest saved


def test_transcribe_with_a_db_that_has_no_settings_table_yet_exits_with_the_message(prompt_files, cli_db):
    with cli_db() as db:
        db.execute(text("DROP TABLE app_settings"))
        db.commit()

    with pytest.raises(SystemExit, match="Choose a transcription model on the Settings page first."):
        transcribe("page.jpg", "main")


def test_transcribe_reads_with_the_texts_it_is_given(prompt_files, monkeypatch):
    """A job passes the db's newest prompt and templates; Windows line endings in the prompt reach the model as plain ones."""
    captured = {}

    def fake_run_claude(image, prompt, template, model, effort):
        captured.update(prompt=prompt, template=template)
        return {"text": "x"}

    monkeypatch.setattr(transcription, "run_claude", fake_run_claude)
    transcribe("page.jpg", "followup", provider="claude", model="sonnet", effort="high",
               texts={"prompt": "Read it.\r\nCarefully.\r\n", "followup": '{"text": null}'})

    assert captured == {"prompt": 'Read it.\nCarefully.\n\n{\n  "text": null\n}', "template": {"text": None}}


def test_cli_runs_with_stdin_closed(monkeypatch):
    seen = {}
    monkeypatch.setattr(transcription.subprocess, "run", lambda command, **kwargs: seen.update(kwargs) or SimpleNamespace(returncode=0))
    run_cli(["codex", "exec", "hi"], "codex")
    assert seen["stdin"] is subprocess.DEVNULL

