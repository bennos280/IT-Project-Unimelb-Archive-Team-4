"""The sign-in status, sign-in, sign-out and test endpoints, with the claude and codex programs faked: nothing real is run."""
import json
import subprocess
import threading
import time
from types import SimpleNamespace

import pytest

from backend.api import connections

STATUS_ARGS = {"/bin/claude": ["auth", "status", "--json"], "/bin/codex": ["login", "status"]}
VERSIONS = {"/bin/claude": "2.1.288 (Claude Code)\n", "/bin/codex": "codex-cli 0.12.3\n"}
SECRET = {"email": "someone@example.com", "orgName": "Secret Org", "orgId": "org-123"}


class FakePopen:
    made = []

    def __init__(self, args, **kwargs):
        self.args, self.kwargs, self.code, self.terminated = args, kwargs, None, False
        FakePopen.made.append(self)

    def poll(self):
        return self.code

    def terminate(self):
        self.terminated, self.code = True, -15

    def wait(self, timeout=None):
        return self.code

    def kill(self):
        self.code = -9


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    """Both programs installed, nothing signed in, and no sign-in running."""
    FakePopen.made = []
    monkeypatch.setattr(connections.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(connections.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(connections.subprocess, "run", lambda *a, **k: pytest.fail("unexpected run"))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    yield
    for _, timer in connections._logins.values():
        timer.cancel()
    connections._logins.clear()


def cli(monkeypatch, claude=None, codex=None, versions=VERSIONS):
    """claude / codex: (exit code, stdout, stderr) the faked status command gives, or an exception to raise.
    versions: what --version prints, or an exception to raise."""
    replies = {"/bin/claude": claude, "/bin/codex": codex}

    def run(args, **kwargs):
        assert kwargs["timeout"] == 10 and kwargs["capture_output"] and kwargs["creationflags"] == connections.NO_WINDOW
        if args[1:] == ["--version"]:
            if isinstance(versions[args[0]], Exception):
                raise versions[args[0]]
            return SimpleNamespace(returncode=0, stdout=versions[args[0]], stderr="")
        assert args[1:] == STATUS_ARGS[args[0]]
        reply = replies[args[0]]
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(returncode=reply[0], stdout=reply[1], stderr=reply[2])
    monkeypatch.setattr(connections.subprocess, "run", run)


def claude_json(**fields):
    return (0, json.dumps({"loggedIn": True, "authMethod": "claude.ai", "subscriptionType": "max", **SECRET, **fields}), "")


def test_claude_signed_in_returns_no_email_or_org(client, monkeypatch):
    cli(monkeypatch, claude=claude_json(), codex=(1, "", "Not logged in"))
    response = client.get("/connections")
    body = response.json()["claude"]
    assert body == {"installed": True, "signedIn": True, "method": "claude.ai", "plan": "max", "version": "2.1.288", "warnings": [],
                    "error": None, "login": {"running": False, "exitCode": None}}
    for secret in SECRET.values():
        assert secret not in response.text


def test_claude_logged_out_exits_1_with_json(client, monkeypatch):
    cli(monkeypatch, claude=(1, json.dumps({"loggedIn": False, "authMethod": "none"}), ""), codex=(1, "", ""))
    body = client.get("/connections").json()["claude"]
    assert (body["installed"], body["signedIn"], body["method"], body["error"]) == (True, False, None, None)


def test_not_installed(client, monkeypatch):
    monkeypatch.setattr(connections.shutil, "which", lambda name: None)
    body = client.get("/connections").json()
    for provider in ("claude", "codex"):
        assert body[provider]["installed"] is False and body[provider]["signedIn"] is False and body[provider]["error"] is None
        assert body[provider]["version"] is None


def test_claude_api_key_method_warns(client, monkeypatch):
    cli(monkeypatch, claude=claude_json(authMethod="api_key", subscriptionType=None), codex=(1, "", ""))
    body = client.get("/connections").json()["claude"]
    assert body["signedIn"] is True and body["method"] == "api_key" and body["plan"] is None
    assert len(body["warnings"]) == 1 and "API key" in body["warnings"][0]


def test_anthropic_api_key_env_warns(client, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    cli(monkeypatch, claude=claude_json(), codex=(1, "", ""))
    response = client.get("/connections")
    assert "ANTHROPIC_API_KEY" in response.json()["claude"]["warnings"][0]
    assert "sk-ant-test" not in response.text


@pytest.mark.parametrize("reply", [(0, "not json", ""), (0, "[1]", ""), (0, "{}", ""), subprocess.TimeoutExpired("claude", 10)])
def test_claude_status_that_fails_is_an_error(client, monkeypatch, reply):
    cli(monkeypatch, claude=reply, codex=(1, "", ""))
    body = client.get("/connections").json()["claude"]
    assert body["signedIn"] is False and "failed" in body["error"]


def test_codex_chatgpt(client, monkeypatch):
    cli(monkeypatch, claude=claude_json(), codex=(0, "", "Logged in using ChatGPT\n"))
    body = client.get("/connections").json()["codex"]
    assert (body["signedIn"], body["method"], body["plan"], body["warnings"]) == (True, "chatgpt", None, [])


def test_codex_api_key_warns_and_hides_the_key(client, monkeypatch):
    cli(monkeypatch, claude=claude_json(), codex=(0, "", "Logged in using an API key - sk-proj-***abcd\n"))
    response = client.get("/connections")
    body = response.json()["codex"]
    assert (body["signedIn"], body["method"]) == (True, "api_key") and "API key" in body["warnings"][0]
    assert "sk-proj" not in response.text and "abcd" not in response.text


def test_codex_not_signed_in(client, monkeypatch):
    cli(monkeypatch, claude=claude_json(), codex=(1, "", "Not logged in\n"))
    body = client.get("/connections").json()["codex"]
    assert (body["signedIn"], body["method"], body["error"]) == (False, None, None)


def test_the_two_status_checks_run_at_the_same_time(client, monkeypatch):
    both_running = threading.Barrier(2, timeout=5)

    def run(args, **kwargs):
        both_running.wait()  #raises unless the other check is running too
        return SimpleNamespace(returncode=1, stdout=json.dumps({"loggedIn": False}), stderr="")
    monkeypatch.setattr(connections.subprocess, "run", run)
    assert client.get("/connections").status_code == 200


def test_a_sign_in_that_ends_during_the_status_check_is_still_reported_running(client, monkeypatch):
    client.post("/connections/claude/login", json={})

    def run(args, **kwargs):
        FakePopen.made[0].code = 0  #the sign-in finishes while the (older) status is being read
        return SimpleNamespace(returncode=1, stdout=json.dumps({"loggedIn": False}), stderr="")
    monkeypatch.setattr(connections.subprocess, "run", run)
    assert client.get("/connections").json()["claude"]["login"]["running"] is True
    assert client.get("/connections").json()["claude"]["login"] == {"running": False, "exitCode": 0}


@pytest.mark.parametrize("provider, args", [("claude", ["auth", "login", "--claudeai"]), ("codex", ["login"])])
def test_login_starts_one_process_with_discarded_output(client, provider, args):
    first = client.post(f"/connections/{provider}/login", json={})
    second = client.post(f"/connections/{provider}/login", json={})
    assert first.status_code == second.status_code == 202
    assert first.json() == second.json() == {"running": True, "exitCode": None}
    assert len(FakePopen.made) == 1
    proc = FakePopen.made[0]
    assert proc.args == [f"/bin/{provider}", *args]
    assert [proc.kwargs[k] for k in ("stdin", "stdout", "stderr")] == [subprocess.DEVNULL] * 3
    assert proc.kwargs["creationflags"] == connections.NO_WINDOW


def test_login_keeps_its_exit_code_until_the_next_start(client, monkeypatch):
    client.post("/connections/codex/login", json={})
    FakePopen.made[0].code = 1
    cli(monkeypatch, claude=claude_json(), codex=(1, "", ""))
    assert client.get("/connections").json()["codex"]["login"] == {"running": False, "exitCode": 1}
    client.post("/connections/codex/login", json={})
    assert len(FakePopen.made) == 2
    assert client.get("/connections").json()["codex"]["login"] == {"running": True, "exitCode": None}


def test_delete_terminates_only_that_process(client, monkeypatch):
    client.post("/connections/claude/login", json={})
    client.post("/connections/codex/login", json={})
    claude, codex = FakePopen.made
    assert client.delete("/connections/claude/login").status_code == 204
    assert claude.terminated and not codex.terminated
    cli(monkeypatch, claude=claude_json(), codex=(1, "", ""))
    body = client.get("/connections").json()
    assert body["claude"]["login"] == {"running": False, "exitCode": None}
    assert body["codex"]["login"]["running"] is True
    assert client.delete("/connections/claude/login").status_code == 204  #nothing running is fine


def test_forgotten_login_is_ended(client, monkeypatch):
    monkeypatch.setattr(connections, "LOGIN_SECONDS", 0.05)
    client.post("/connections/claude/login", json={})
    deadline = time.time() + 5
    while not FakePopen.made[0].terminated and time.time() < deadline:
        time.sleep(0.01)
    assert FakePopen.made[0].terminated


def test_unknown_provider_is_404(client):
    assert client.post("/connections/gemini/login", json={}).status_code == 404
    assert client.delete("/connections/gemini/login").status_code == 404


def test_login_for_a_missing_program_is_409(client, monkeypatch):
    monkeypatch.setattr(connections.shutil, "which", lambda name: None)
    assert client.post("/connections/claude/login", json={}).status_code == 409
    assert FakePopen.made == []


def test_login_without_a_json_body_is_rejected(client):
    assert client.post("/connections/claude/login").status_code in (415, 422)
    form = client.post("/connections/claude/login", content="{}", headers={"Content-Type": "text/plain"})
    assert form.status_code in (415, 422)
    assert FakePopen.made == []


# versions
def test_versions_are_the_first_x_y_z_of_version_output(client, monkeypatch):
    cli(monkeypatch, claude=claude_json(), codex=(1, "", ""), versions={"/bin/claude": "Claude Code v12.0.1 (build 3.4.5)", "/bin/codex": "codex-cli 0.12.3\n"})
    body = client.get("/connections").json()
    assert (body["claude"]["version"], body["codex"]["version"]) == ("12.0.1", "0.12.3")


@pytest.mark.parametrize("versions", [{"/bin/claude": "no number", "/bin/codex": ""},
                                      {"/bin/claude": subprocess.TimeoutExpired("claude", 10), "/bin/codex": OSError()}])
def test_a_version_that_cannot_be_read_is_none_and_nothing_else_changes(client, monkeypatch, versions):
    cli(monkeypatch, claude=claude_json(), codex=(0, "", "Logged in using ChatGPT"), versions=versions)
    body = client.get("/connections").json()
    assert body["claude"]["version"] is None and body["codex"]["version"] is None
    assert body["claude"]["signedIn"] is True and body["codex"]["signedIn"] is True
    assert body["claude"]["warnings"] == []


@pytest.mark.parametrize("version, warned", [("2.1.279", True), ("2.0.999", True), ("1.99.999", True),
                                             ("2.1.280", False), ("2.1.1000", False), ("2.2.0", False), ("10.0.0", False)])
def test_old_claude_warns(client, monkeypatch, version, warned):
    cli(monkeypatch, claude=claude_json(), codex=(1, "", ""), versions={"/bin/claude": f"{version} (Claude Code)", "/bin/codex": "codex-cli 0.0.1"})
    body = client.get("/connections").json()
    expected = [f"Claude Code {version} is older than 2.1.280, which transcription needs. Update it with: claude update"]
    assert body["claude"]["warnings"] == (expected if warned else [])
    assert body["codex"]["warnings"] == []  #no minimum for codex


def test_old_claude_warns_when_signed_out_too(client, monkeypatch):
    cli(monkeypatch, claude=(1, json.dumps({"loggedIn": False}), ""), codex=(1, "", ""),
        versions={"/bin/claude": "2.0.0 (Claude Code)", "/bin/codex": "codex-cli 0.0.1"})
    assert len(client.get("/connections").json()["claude"]["warnings"]) == 1


# sign-out
@pytest.fixture
def logout(monkeypatch):
    """Faked claude / codex whose logout command signs them out; run.ran holds the commands that were run."""
    state, ran = {"/bin/claude": True, "/bin/codex": True}, []

    def run(args, **kwargs):
        ran.append((args, kwargs))
        if args[1:] == ["--version"]:
            return SimpleNamespace(returncode=0, stdout=VERSIONS[args[0]], stderr="")
        if args[1:] in (["auth", "logout"], ["logout"]):
            if state.get("fail"):
                return SimpleNamespace(returncode=1, stdout="", stderr="could not log out")
            state[args[0]] = False
            return SimpleNamespace(returncode=0, stdout="Logged out as " + SECRET["email"], stderr="")
        if args[0] == "/bin/claude":
            return SimpleNamespace(returncode=0 if state[args[0]] else 1, stdout=json.dumps({
                "loggedIn": state[args[0]], "authMethod": "claude.ai", "subscriptionType": "max", **SECRET}), stderr="")
        return SimpleNamespace(returncode=0 if state[args[0]] else 1, stdout="", stderr="Logged in using ChatGPT")
    monkeypatch.setattr(connections.subprocess, "run", run)
    run.state, run.ran = state, ran
    return run


@pytest.mark.parametrize("provider, args", [("claude", ["auth", "logout"]), ("codex", ["logout"])])
def test_logout_runs_only_the_programs_own_logout_and_returns_the_new_status(client, logout, provider, args):
    response = client.post(f"/connections/{provider}/logout", json={})
    assert response.status_code == 200
    body = response.json()
    assert (body["installed"], body["signedIn"], body["method"], body["plan"]) == (True, False, None, None)
    commands = [(a, k) for a, k in logout.ran if a[1:] == args]
    assert len(commands) == 1
    assert commands[0][0] == [f"/bin/{provider}", *args]
    assert commands[0][1]["timeout"] == 15 and commands[0][1]["capture_output"] and commands[0][1]["creationflags"] == connections.NO_WINDOW
    assert SECRET["email"] not in response.text and "Logged out" not in response.text
    other = "codex" if provider == "claude" else "claude"
    assert logout.state[f"/bin/{other}"] is True  #only this provider is signed out


def test_logout_that_leaves_the_program_signed_in_is_an_error(client, logout):
    logout.state["fail"] = True
    response = client.post("/connections/claude/logout", json={})
    assert response.status_code == 500 and "could not log out" not in response.text


def test_logout_that_times_out_is_an_error(client, monkeypatch):
    def run(args, **kwargs):
        raise subprocess.TimeoutExpired(args, kwargs["timeout"])
    monkeypatch.setattr(connections.subprocess, "run", run)
    assert client.post("/connections/codex/logout", json={}).status_code == 500


def test_logout_unknown_provider_404_and_missing_program_409(client, monkeypatch):
    assert client.post("/connections/gemini/logout", json={}).status_code == 404
    monkeypatch.setattr(connections.shutil, "which", lambda name: None)
    assert client.post("/connections/claude/logout", json={}).status_code == 409


def test_logout_without_a_json_body_is_rejected(client, logout):
    assert client.post("/connections/claude/logout").status_code in (415, 422)
    form = client.post("/connections/claude/logout", content="{}", headers={"Content-Type": "text/plain"})
    assert form.status_code in (415, 422)
    assert logout.ran == [] and logout.state["/bin/claude"] is True


# test connection
@pytest.fixture
def ask(monkeypatch):
    """Faked requests: set ask.reply to (exit code, stdout, stderr) or an exception; ask.sent holds what was run."""
    def run(args, **kwargs):
        ask.sent.append((args, kwargs))
        if isinstance(ask.reply, Exception):
            raise ask.reply
        return SimpleNamespace(returncode=ask.reply[0], stdout=ask.reply[1], stderr=ask.reply[2])
    ask.sent, ask.reply = [], (0, "", "")
    monkeypatch.setattr(connections.subprocess, "run", run)
    return ask


CLAUDE_OK = json.dumps({"type": "result", "is_error": False, "result": "ok", "session_id": "s-123", **SECRET})
FIELDS = {"ok", "seconds", "model", "message"}


def test_claude_test_uses_the_default_model_when_the_default_is_claude(client, db, ask):
    from backend.db import app_settings
    app_settings.save_transcription_defaults(db, "claude", "opus", "high")
    ask.reply = (0, CLAUDE_OK, "")
    response = client.post("/connections/claude/test", json={})
    body = response.json()
    assert response.status_code == 200 and set(body) == FIELDS
    assert body["ok"] is True and body["model"] == "opus" and body["message"] == f"Replied in {body['seconds']} s"
    [(args, kwargs)] = ask.sent
    assert args == ["/bin/claude", "-p", "Reply with the single word: ok", "--model", "opus", "--effort", "low", "--output-format", "json",
                    "--strict-mcp-config", "--safe-mode", "--tools", ""]
    assert kwargs["timeout"] == 90 and kwargs["capture_output"] and kwargs["creationflags"] == connections.NO_WINDOW
    assert kwargs["cwd"] and "IT-Project" not in kwargs["cwd"]  #a throwaway folder, not the project
    for secret in (*SECRET.values(), "s-123"):
        assert secret not in response.text


def test_claude_test_uses_haiku_when_the_default_is_codex(client, db, ask):
    from backend.db import app_settings
    app_settings.save_transcription_defaults(db, "codex", "gpt-5", "high")
    ask.reply = (0, CLAUDE_OK, "")
    assert client.post("/connections/claude/test", json={}).json()["model"] == "haiku"
    assert ask.sent[0][0][4] == "haiku"


def test_codex_test_uses_the_default_model_if_codex_else_its_own(client, db, ask):
    from backend.db import app_settings
    ask.reply = (0, "OK in plenty of private text", "banner")
    response = client.post("/connections/codex/test", json={})
    assert response.json()["model"] == "default" and "private" not in response.text and "banner" not in response.text
    assert ask.sent[0][0] == ["/bin/codex", "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "Reply with the single word: ok"]
    app_settings.save_transcription_defaults(db, "codex", "gpt-5", "high")
    assert client.post("/connections/codex/test", json={}).json()["model"] == "gpt-5"
    assert ask.sent[1][0] == ["/bin/codex", "exec", "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only", "--model", "gpt-5",
                              "Reply with the single word: ok"]


def test_claude_error_result_is_cut_to_200_characters_and_nothing_else_returns(client, ask):
    ask.reply = (1, json.dumps({"is_error": True, "result": "Not logged in. " + "x" * 300, "session_id": "s-123", **SECRET}), "stderr text")
    response = client.post("/connections/claude/test", json={})
    body = response.json()
    assert set(body) == FIELDS and body["ok"] is False and body["message"] == ("Not logged in. " + "x" * 300)[:200]
    for secret in (*SECRET.values(), "s-123", "stderr text"):
        assert secret not in response.text


@pytest.mark.parametrize("reply", [(1, "not json", "boom"), (0, "[1]", ""), (0, json.dumps({"is_error": True}), "")])
def test_claude_failures_without_a_result_still_give_a_message(client, ask, reply):
    ask.reply = reply
    body = client.post("/connections/claude/test", json={}).json()
    assert body["ok"] is False and body["message"]


def test_codex_failure_gives_the_end_of_its_error(client, ask):
    ask.reply = (1, "", "banner " * 100 + "ERROR: not signed in")
    body = client.post("/connections/codex/test", json={}).json()
    assert body["ok"] is False and body["message"].endswith("ERROR: not signed in") and len(body["message"]) == 200


def test_a_test_that_times_out_says_so_and_can_be_run_again(client, ask):
    ask.reply = subprocess.TimeoutExpired("claude", 90)
    body = client.post("/connections/claude/test", json={}).json()
    assert body["ok"] is False and "90 seconds" in body["message"] and set(body) == FIELDS
    ask.reply = (0, CLAUDE_OK, "")
    assert client.post("/connections/claude/test", json={}).json()["ok"] is True


def test_a_program_that_cannot_start_is_a_failed_test(client, ask):
    ask.reply = OSError("no")
    body = client.post("/connections/codex/test", json={}).json()
    assert body["ok"] is False and body["message"] == "Could not run the program."


def test_one_test_per_provider_at_a_time(client, monkeypatch):
    started, release = threading.Event(), threading.Event()

    def run(args, **kwargs):
        started.set()
        assert release.wait(5)
        return SimpleNamespace(returncode=0, stdout=CLAUDE_OK, stderr="")
    monkeypatch.setattr(connections.subprocess, "run", run)
    first = {}
    thread = threading.Thread(target=lambda: first.update(r=client.post("/connections/claude/test", json={})))
    thread.start()
    try:
        assert started.wait(5)
        assert client.post("/connections/claude/test", json={}).status_code == 409
    finally:
        release.set()
        thread.join(5)
    assert first["r"].status_code == 200
    assert client.post("/connections/claude/test", json={}).status_code == 200  #free again


def test_test_unknown_provider_404_missing_program_409_and_json_body_required(client, ask, monkeypatch):
    assert client.post("/connections/gemini/test", json={}).status_code == 404
    assert client.post("/connections/claude/test").status_code in (415, 422)
    assert client.post("/connections/claude/test", content="{}", headers={"Content-Type": "text/plain"}).status_code in (415, 422)
    monkeypatch.setattr(connections.shutil, "which", lambda name: None)
    assert client.post("/connections/claude/test", json={}).status_code == 409
    assert ask.sent == []


def test_cli_checks_run_with_stdin_closed(monkeypatch):
    import subprocess
    from backend.api import connections
    seen = {}
    monkeypatch.setattr(connections.subprocess, "run", lambda command, **kwargs: seen.update(kwargs))
    connections.run_cli("codex", "exec", "hi")
    assert seen["stdin"] is subprocess.DEVNULL

