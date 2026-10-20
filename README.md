# PrestCribe

Turns scanned records from the University of Melbourne Archives into checked, searchable data: add a series, set it up on one
sample item, read the rest, then check each record.

## Setup

1. Install **uv once** on your computer. On Windows:

   ```powershell
   winget install --id=astral-sh.uv -e
   ```

   For Mac/Linux or other installation options, see the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

2. Put your survey PDFs ([the archive](https://archives.library.unimelb.edu.au/nodes/view/499420)) in the project's `data` folder. If they live on another drive, make `data` a folder link to them. Results are saved in the project's `output` folder, under `output/<name>/`; the default run skips inputs only when their requested steps are complete. Both folders are fixed, inside the project, and ignored by git. Before transcribing, choose the provider, model and effort on the Settings page (see below): there is no default.

3. Run the pipeline:

   ```sh
   uv run survey
   ```

   The first run automatically creates the Python environment and installs the required libraries; later runs reuse it. No separate `uv sync` step is needed. After setup, just run `uv run survey` from the project folder.

## Commands

| Command                                                          | Description                                                                                                                                                                                                    |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uv run survey`                                                  | Process new or unfinished PDFs (or folders of page images) in `data` → `output/<name>/manifest.json` + `review.json`                                                                                         |
| `uv run survey x.pdf`                                            | Process one PDF or a folder of page images; `--transcribe` also transcribes and groups pages into surveys by dwelling number (paid: needs the `claude` CLI (Claude Code 2.1.280+) signed in, or OpenAI's `codex` CLI chosen on the Settings page)                                                             |
| `uv run pytest`                                                  | Run all tests (see `tests/README.md` for more info) scored                                                                                                      |
| `uv run survey train`                                            | Refit identification after adding pages under `tests/identify/pages/<label>/` (foreign forms: `other/`)                                                                                                        |
| `uv run python -m backend.db.loader` | Load finished runs in `OUTPUT` into the database (`backend/db/prestcribe.db`), creating or upgrading it first |
| `uv run app` | Start the API (every endpoint is listed, and can be tried, at http://127.0.0.1:8000/docs) and the worker that runs the jobs queued with `POST /jobs`; Ctrl+C stops both |
| `uv run api` / `uv run worker` | Just one of the two (the API restarts when you save code) |
| `uv run alembic revision --autogenerate -m "what changed"` | After changing the tables in `backend/db/models.py`; a database upgrades itself on its next load, backed up first |

A bundle's PDF, or a page's scan, that isn't on this computer is downloaded from [the archive](https://archives.library.unimelb.edu.au/nodes/view/499420) and kept.

If a run stops partway through, run the same command again. Splitting and identification run again for unfinished inputs. With `--transcribe`, saved page transcripts are reused when the image, page type, model, effort, prompt and template still match and the saved result is unchanged. Adding `--transcribe` also picks up inputs that have finished identification but have not finished transcription.

If you replace a PDF that was already completed, pass its path explicitly to rerun it, for example `uv run survey data/x.pdf`. The generated page folder is replaced after the new PDF renders successfully, so pages from an older, longer PDF are removed.

## UI Setup

Install **Node.js 24.x** (includes npm), alongside the Python setup above. Run these commands from the project folder:

| Command                                                     | Description                                        |
| ----------------------------------------------------------- | -------------------------------------------------- |
| `npm --prefix frontend ci`                                  | Install frontend dependencies before the first run |
| `uv run app`                                                | Start the backend                                  |
| `npm --prefix frontend run dev -- --port 5174 --strictPort` | Start the frontend in a second terminal            |

Keep both terminals running and open [the review UI](http://localhost:5174/).

Transcription runs Claude Code or the Codex CLI on your computer, so each team member signs in with their own subscription. The Settings page (gear button on the dashboard) shows the sign-in status and opens the official sign-in in your browser. The app never sees your credentials. Usage counts against your own subscription. It is also where you choose the provider, model and effort for every transcription, in the app and with `uv run survey --transcribe`. They are saved in the database (shared with the team once it is committed) and have no default: until they are chosen, transcribing stops with "Choose a transcription model on the Settings page first." A model picked in a transcription dialog applies to that run only. The Settings page also shows where the scans and results folders are.

## Add a step

A step is one function in `backend/pipeline/run.py` that reads and writes `run.pages`, plus one entry in `STEPS`:

```python
def step_thing(run):
    for page in run.pages:
        page["thing"] = ...
        if unsure:
            run.flag(page, "thing", "why")

STEPS = {"split": step_split, "identify": step_identify, "thing": step_thing, "transcribe": step_transcribe, "group": step_group}
```

Heavy code goes in `backend/pipeline/thing/`, imported inside the function. Flagged pages land in `review.json`.
