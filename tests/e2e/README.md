# End-to-end tests

The whole system behind a pipeline job: the API, the worker, the pipeline, the loader and the real database tables
(built by the migrations). Only page sorting (a GPU model) and the paid model call are faked, so these run in CI.

```bash
uv run pytest tests/e2e
```

## `test_pipeline_job.py`

| Test | What it checks |
|---|---|
| `test_queued_bundle_comes_back_as_surveys` | A 4-page PDF (two surveys, numbered 7 and 9) is listed by `GET /bundles`, queued with `POST /jobs`, and run by the worker through the real split, group and loader steps into tables built by the migrations. It then shows as loaded with a done job of 4/4 pages and its surveys in scan order (`bundle-7`, `bundle-9`). `GET /survey/bundle-9` returns its main form and coded card, the main form's `imageUrl` serves a PNG scan, and the address field holds the transcribed "9 Peel St."; running the bundle again is refused (409). |

## Manual check with the real model (paid)

Before a demo, or after changing the pipeline, run one real bundle. A 130-page bundle takes about 15 minutes.

1. Start the app with `uv run app` (the API and the worker).
2. Open http://127.0.0.1:8000/docs and queue a bundle that isn't loaded yet with `POST /jobs` (its `pdf` as `GET /bundles` lists it).
3. Watch it go with `GET /bundles`: its job's `step` moves from split to transcribe (with `donePages`/`totalPages`), then the bundle shows `loaded` with its `surveys`.
4. Open `http://127.0.0.1:8000/survey/<one of those survey ids>`: it should list its main form, notes and coded card.
5. Optional: press Ctrl+C mid-run, run `uv run app` again and queue the bundle again. The job is marked failed when stopped, then carries on without paying again for pages already read.
