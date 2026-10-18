# Prest survey digitisation (Team 4)

Turns the 1940s University of Melbourne social survey scans into reviewed data: each page is sorted (main / notes / coded / blank), transcribed by a vision model, grouped into surveys and checked, then reviewed in the browser.

## Setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (Windows: `winget install --id=astral-sh.uv -e`) and [Node.js 24](https://nodejs.org/).
2. Install the frontend once: `npm --prefix frontend ci`
3. Put the survey PDFs ([the archive](https://archives.library.unimelb.edu.au/nodes/view/499420)) in the project's `data` folder; results go in `output`. Both stay inside the project and git ignores them. If the scans live on another drive, make `data` a folder link to them.

## Run

```sh
uv run app                        # API and worker
npm --prefix frontend run dev     # in a second terminal, then open http://localhost:5173
```

On first use, open **Settings** (gear button on the dashboard): sign Claude Code or the Codex CLI in with your own subscription, and choose the transcription provider, model and effort. Nothing transcribes until they are chosen.

## Commands

| Command | Does |
| --- | --- |
| `uv run survey` | Process new or unfinished PDFs in `data`; add `--transcribe` to transcribe and group them too |
| `uv run survey data/x.pdf` | Process one PDF (or a folder of page images) |
| `uv run survey train` | Refit page sorting after adding pages under `tests/identify/pages/<label>/` |
| `uv run python -m backend.db.loader` | Load finished runs from `output` into the database |
| `uv run api` / `uv run worker` | Start just the API (reloads on save) or just the worker |
| `uv run alembic revision --autogenerate -m "what changed"` | Add a migration after changing `backend/db/models.py` |

A stopped run picks up where it left off when run again. API endpoints are listed at http://127.0.0.1:8000/docs.

## Tests

```sh
uv run pytest tests/unit tests/integration tests/e2e   # backend: unit, integration, end-to-end
npm --prefix tests ci                                   # once, for the frontend tests
npm --prefix tests exec -- playwright install chromium  # once, the browser they run in
npm --prefix tests run test:all                         # frontend: lint, build, unit, browser and adapter tests
```

CI (`.github/workflows/tests.yml`) runs all of them on every pull request.
