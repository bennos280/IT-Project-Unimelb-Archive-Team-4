# Prest survey digitisation (Team 4)

1940s University of Melbourne social survey scans -> data. Each PDF page is labelled
(main / notes / coded / blank, or **review** when the model isn't sure) and, optionally,
transcribed to JSON by a vision model. Pages a human must check land in `review.json`.

## Setup

1. Install **uv once** on your computer. On Windows:

   ```powershell
   winget install --id=astral-sh.uv -e
   ```

   For Mac/Linux or other installation options, see the [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).

2. Open a **new terminal in the project folder** and copy the configuration:

   ```powershell
   Copy-Item .env.example .env
   ```

   On Mac/Linux, use `cp .env.example .env`.

3. Set `DATA` in `.env` to your folder of survey PDFs ([the archive](https://archives.library.unimelb.edu.au/nodes/view/499420)). To use the default `DATA=data`, create a `data` folder inside the project and put your PDFs there.

   Set `OUTPUT` to where pipeline results should be saved (default: `output`). Both `DATA` and `OUTPUT` accept paths relative to the project folder or absolute paths such as `D:/survey-results`. Results go under `<OUTPUT>/<name>/`; the default run skips inputs only when their requested steps are complete. Choosing a new, empty output folder starts a fresh set of results.

4. Run the pipeline:

   ```sh
   uv run survey
   ```

   The first run automatically creates the Python environment and installs the required libraries; later runs reuse it. No separate `uv sync` step is needed. After setup, just run `uv run survey` from the project folder.

## Commands

| Command                                                          | Description                                                                                                                                                                                                    |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `uv run survey`                                                  | Process new or unfinished PDFs (or folders of page images) in `DATA` → `<OUTPUT>/<name>/manifest.json` + `review.json`                                                                                         |
| `uv run survey x.pdf`                                            | Process one PDF or a folder of page images; `--transcribe` also transcribes and groups pages into surveys by dwelling number (paid: needs the `claude` CLI signed in, or `codex` for gpt-\* models)                                                             |
| `uv run pytest`                                                  | Run all tests (see `tests/README.md` for more info) scored                                                                                                      |
| `uv run survey train`                                            | Refit identification after adding pages under `tests/identify/pages/<label>/` (foreign forms: `other/`)                                                                                                        |
| `uv run survey transcribe <card>`, `uv run survey score --pages` | Run transcription/scoring and view the transcription leaderboard in `results/transcribe/`                                                                                                                      |
| `uv run survey data/x.pdf --preprocess`                          | Identify pages, then crop, straighten, and binarize eligible page images                                                                                                                                       |
| `uv run survey data/x.pdf --preprocess --transcribe`             | Identify and preprocess eligible page images, then transcribe them to JSON                                                                                                                                     |
| ↳ Optional enhancements                                          | `--greyscale` converts to greyscale; `--binarize` converts to black and white; `--no-deskew` skips deskewing; `--no-crop` skips cropping; `--c <num>` adjusts the adaptive threshold constant (e.g. `--c 12`). |

If a run stops partway through, run the same command again. Splitting and identification run again for unfinished inputs. With `--transcribe`, saved page transcripts are reused when the image, page type, model, effort, prompt and template still match and the saved result is unchanged. Adding `--transcribe` also picks up inputs that have finished identification but have not finished transcription.

If you replace a PDF that was already completed, pass its path explicitly to rerun it, for example `uv run survey data/x.pdf`. The generated page folder is replaced after the new PDF renders successfully, so pages from an older, longer PDF are removed.

## Add a step

A step is one function in `pipeline/run.py` that reads and writes `run.pages`, plus one entry in `STEPS`:

```python
def step_thing(run):
    for page in run.pages:
        page["thing"] = ...
        if unsure:
            run.flag(page, "thing", "why")

STEPS = {"split": step_split, "identify": step_identify,"preprocess": step_preprocess, "thing": step_thing, "transcribe": step_transcribe}
```

Heavy code goes in `pipeline/thing/`, imported inside the function. Flagged pages land in `review.json`.
