# Prest survey digitisation (Team 4)

A tool for turning the University of Melbourne's 1940s social survey scans into structured, reviewable data. It classifies pages, transcribes them with a vision model, groups them into surveys and checks for inconsistencies before human review in the browser.

## Workflow

**Scans → Page classification → Transcription → Survey grouping → Consistency checks → Human review**

Pages are classified as main forms, notes, coded cards or blanks; uncertain classifications are sent for review. Consistency checks flag possible contradictions without changing the transcribed values. Reviewers inspect the scans and readings, save corrections and export data.

## Setup

Run commands from the project root.

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (Windows: `winget install --id=astral-sh.uv -e`) and [Node.js 24](https://nodejs.org/).
2. Install frontend dependencies: `npm --prefix frontend ci`.
3. Put survey PDFs from [University of Melbourne Archives](https://archives.library.unimelb.edu.au/nodes/view/499420) in `data`. Results are written to `output`. Both folders are inside the project and ignored by Git; `data` can be a folder link if scans are stored on another drive.

The first `uv run` command creates the Python environment and installs its dependencies.

## Run

Start the backend and frontend in separate terminals:

```sh
uv run app
npm --prefix frontend run dev
```

Keep both terminals running and open the URL printed by the frontend (normally http://localhost:5173).

Before transcribing, open **Settings** using the dashboard's gear button. Sign in to Claude Code or the Codex CLI with your own subscription, then select the provider, model and effort. There is no default transcription choice; usage counts against your subscription. These settings also apply to CLI transcription.

## Common commands

| Command | Purpose |
| --- | --- |
| `uv run survey` | Process new or unfinished inputs in `data` |
| `uv run survey --transcribe` | Also transcribe and group pages using the selected model |
| `uv run survey data/x.pdf --transcribe` | Process and transcribe a specific PDF; a folder of page images is also accepted |
| `uv run python -m backend.db.loader` | Load finished runs from `output` into the database |

To resume an interrupted pipeline run, repeat the command. Saved transcripts are reused when their inputs and transcription settings still match. To rerun a replaced PDF that was already completed, pass its path explicitly.

API endpoints can be explored at http://127.0.0.1:8000/docs while the backend is running.

## Tests

```sh
uv run pytest tests/unit tests/integration tests/e2e
npm --prefix tests ci
npm --prefix tests exec -- playwright install chromium
npm --prefix tests run test:all
```

The npm dependency and browser installation commands are needed for initial test setup. CI runs the backend suites and frontend checks on pull requests and pushes to `main`.

## Development

See [Development notes](development.md) for test coverage and individual commands, a manual pipeline check, validation configuration and maintenance tasks.
