"""Test docs/openapi.json is the API's current OpenAPI spec."""
import json

from backend.api.main import app
from backend.common import ROOT

SPEC = ROOT / "docs" / "openapi.json"


def test_docs_openapi_json_is_the_apis_current_spec():
    current = json.loads(json.dumps(app.openapi()))
    if json.loads(SPEC.read_text(encoding="utf-8")) != current:
        SPEC.write_text(json.dumps(current, indent=2) + "\n", encoding="utf-8")
        raise AssertionError("docs/openapi.json was out of date and has been re-exported; commit it")
