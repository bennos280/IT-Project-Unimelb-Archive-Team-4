"""Transcription through an AI company's API with your own key, or a model on this computer (Ollama), besides the claude and
codex programs (transcribe.py). One page image and the prompt go in; the filled template comes back. Keys are kept in
~/.prestcribe/keys.json (or the usual environment variable), never in the database, so a PrestCribe file doesn't carry them."""
import base64
import io
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

#id -> what people see, the environment variable a key may also come from (None: no key), the API's address, where to get a key
PROVIDERS = {
    "anthropic": {"label": "Claude API", "env": "ANTHROPIC_API_KEY", "url": "https://api.anthropic.com/v1",
                  "keys": "https://console.anthropic.com/settings/keys"},
    "openai": {"label": "OpenAI API", "env": "OPENAI_API_KEY", "url": "https://api.openai.com/v1",
               "keys": "https://platform.openai.com/api-keys"},
    "gemini": {"label": "Gemini API", "env": "GEMINI_API_KEY", "url": "https://generativelanguage.googleapis.com/v1beta/openai",
               "keys": "https://aistudio.google.com/apikey"},
    "openrouter": {"label": "OpenRouter", "env": "OPENROUTER_API_KEY", "url": "https://openrouter.ai/api/v1",
                   "keys": "https://openrouter.ai/settings/keys"},
    "ollama": {"label": "Ollama (this computer)", "env": None, "url": "http://127.0.0.1:11434/v1", "keys": "https://ollama.com/download"},
}
KEYS = Path.home() / ".prestcribe" / "keys.json"
TIMEOUT = 600  #seconds one page may take
LONGEST = 1600  #pixels: a page is sent no bigger, as JPEG (APIs refuse large images; Claude reads up to about this)
#model names that can't read a page image, left out of the lists
NOT_VISION = ("embed", "tts", "whisper", "dall-e", "audio", "realtime", "transcribe", "moderation", "image", "search", "davinci",
              "babbage", "aqa", "imagen", "veo", "computer-use")


def saved_keys():
    try:
        return json.loads(KEYS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


#a provider's key: saved here, else its environment variable; "" for Ollama, None if there is none
def key(provider):
    env = PROVIDERS[provider]["env"]
    if env is None:
        return ""
    return saved_keys().get(provider) or os.environ.get(env) or None


def save_key(provider, value):
    keys = saved_keys()
    if value:
        keys[provider] = value
    else:
        keys.pop(provider, None)
    KEYS.parent.mkdir(parents=True, exist_ok=True)
    KEYS.write_text(json.dumps(keys, indent=2), encoding="utf-8")


def request(provider, path, body=None, timeout=TIMEOUT):
    """The API's JSON answer to a GET (no body) or POST; an error raises urllib.error.HTTPError or URLError."""
    secret = key(provider)
    headers = {"Content-Type": "application/json", "User-Agent": "PrestCribe"}
    if provider == "anthropic":
        headers |= {"x-api-key": secret or "", "anthropic-version": "2023-06-01"}
    elif secret:
        headers["Authorization"] = f"Bearer {secret}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    with urllib.request.urlopen(urllib.request.Request(PROVIDERS[provider]["url"] + path, data, headers), timeout=timeout) as reply:
        return json.loads(reply.read().decode("utf-8"))


def failed(provider, error):
    """Exits with what the API said went wrong (a job fails with it), never the key."""
    label = PROVIDERS[provider]["label"]
    if isinstance(error, urllib.error.HTTPError):
        detail = error.read().decode("utf-8", "replace")[:400]
        sys.exit(f"{label} refused it (HTTP {error.code}): {detail}")
    sys.exit(f"{label} couldn't be reached ({getattr(error, 'reason', error)})")


def jpeg(image):
    from PIL import Image
    with Image.open(image) as page:
        page = page.convert("RGB")
        page.thumbnail((LONGEST, LONGEST))
        out = io.BytesIO()
        page.save(out, "JPEG", quality=90)
    return base64.b64encode(out.getvalue()).decode("ascii")


def json_in(text):
    """The JSON object in a model's answer, which may come wrapped in a code block."""
    try:
        return json.loads(text[text.find("{"):text.rfind("}") + 1])
    except ValueError:
        sys.exit(f"the model gave no JSON back: {text[:300]}")


def run_api(provider, image, prompt, schema, model):
    """One page image read with prompt; the answer is held to schema (a template's JSON schema) where the API can do that."""
    if provider not in PROVIDERS:
        sys.exit(f"no provider called {provider}")
    if key(provider) is None:
        sys.exit(f"{PROVIDERS[provider]['label']} has no key: add one on the Settings page")
    picture = jpeg(image)
    try:
        if provider == "anthropic":  #its own API: the answer comes as the input of a tool it must use
            reply = request(provider, "/messages", {
                "model": model, "max_tokens": 16000,
                "tools": [{"name": "record", "description": "The filled template.", "input_schema": schema}],
                "tool_choice": {"type": "tool", "name": "record"},
                "messages": [{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": picture}},
                    {"type": "text", "text": prompt}]}]})
            used = next((part for part in reply.get("content", []) if part.get("type") == "tool_use"), None)
            if not used:
                sys.exit(f"Claude API gave no answer: {json.dumps(reply)[:300]}")
            return used["input"]
        body = {"model": model, "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt}, {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{picture}"}}]}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "record", "schema": schema, "strict": True}}}
        try:
            reply = request(provider, "/chat/completions", body)
        except urllib.error.HTTPError as error:  #a model that can't be held to a schema: asked again for JSON in words
            if error.code != 400:
                raise
            body.pop("response_format")
            body["messages"][0]["content"][0]["text"] = f"{prompt}\n\nAnswer with only the JSON object."
            reply = request(provider, "/chat/completions", body)
        return json_in(reply["choices"][0]["message"]["content"] or "")
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        failed(provider, error)


def models(provider):
    """The models a provider offers this key that may read a page image, by name."""
    listed = request(provider, "/models", timeout=20)
    if provider == "openrouter":
        names = [m["id"] for m in listed["data"] if "image" in (m.get("architecture") or {}).get("input_modalities", [])]
    else:
        names = [m["id"].removeprefix("models/") for m in listed.get("data", [])]
    return sorted(n for n in names if not any(word in n for word in NOT_VISION))
