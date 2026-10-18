"""End to end, through the API: a queued bundle goes through the worker, the real split, group and loader
steps and the real database tables, and comes back out of the API as surveys. Only page sorting (a GPU model) and
the paid model call are faked."""
import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from backend.db import database
from backend.api import main
from backend import worker
from backend.pipeline import run
from backend.pipeline.identify import identify
from backend.pipeline.transcribe import transcribe as transcription

# a bundle of two surveys: each a main form and its coded card, numbered 7 and 9 in pencil
PAGES = [("main", "7"), ("coded", "7"), ("main", "9"), ("coded", "9")]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    pdf = tmp_path / "data" / "216441" / "bundle.pdf"
    pdf.parent.mkdir(parents=True)
    with pymupdf.open() as doc:
        for number in range(len(PAGES)):
            doc.new_page(width=100, height=100).insert_text((10, 25), f"page {number + 1}")
        doc.save(pdf)

    config = {"DATA": str(tmp_path / "data"), "OUTPUT": str(tmp_path / "output")}
    for module in (main, worker, run):
        monkeypatch.setattr(module, "settings", lambda: config)
    monkeypatch.setattr(identify, "identify_pages",
                        lambda images, weights=None: [{"label": label, "confidence": 1.0, "distance": 0.0} for label, _ in PAGES])

    def transcribe(image, kind, **options):
        number = PAGES[int(image.stem[-5:]) - 1][1]
        return {"number_of_dwelling": number, "address": f"{number} Peel St.", "provider": "claude",
                "model": "sonnet", "effort": "low", "seconds": 1.0}

    monkeypatch.setattr(transcription, "transcribe", transcribe)

    url = f"sqlite:///{(tmp_path / 'test.db').as_posix()}"
    database.migrate(url)  # the real tables, built the way the real db is
    monkeypatch.setattr(database, "engine", database.make_engine(url))
    db = sessionmaker(autoflush=False, bind=database.engine)()
    main.app.dependency_overrides[main.get_db] = lambda: db
    with TestClient(main.app) as client:
        yield client, db
    main.app.dependency_overrides.clear()
    db.close()


def test_queued_bundle_comes_back_as_surveys(setup):
    client, db = setup
    [bundle] = client.get("/bundles").json()
    assert (bundle["name"], bundle["loaded"], bundle["job"]) == ("216441", False, None)

    assert client.post("/jobs", json={"pdf": bundle["pdf"], "provider": "claude", "model": "sonnet", "effort": "low"}).status_code == 202
    assert worker.work_once(db)  # the worker picks the job up and runs it

    [bundle] = client.get("/bundles").json()
    job = bundle["job"]
    assert (bundle["loaded"], job["status"], job["donePages"], job["totalPages"]) == (True, "done", 4, 4)
    assert bundle["surveys"] == ["bundle-7", "bundle-9"]  # in scan order, for the review screen to list
    survey = client.get("/survey/bundle-9").json()
    assert [page["type"] for page in survey["pages"]] == ["main", "coded"]
    assert client.get(survey["pages"][0]["imageUrl"]).headers["content-type"] == "image/png"
    assert {"id": "address", "label": "Address", "labelText": "Address", "group": "Address", "value": "9 Peel St.",
            "decoded": None} in survey["pages"][0]["fields"]
    assert client.post("/jobs", json={"pdf": bundle["pdf"]}).status_code == 409  # loaded: its reviews are safe
