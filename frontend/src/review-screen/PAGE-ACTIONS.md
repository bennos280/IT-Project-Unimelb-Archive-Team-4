# Page actions (US7)

Open a survey and select a reviewer. Page actions beside Transcribe offers:

- **Move to another survey**: lists only surveys in the current bundle, previews their pages, and permits multiple pages of the same type. Moving keeps the page ID, source image, fields, flags and edits. It records the reviewer, reason, time and old/new survey IDs in `page_moves`, then opens the moved page in its destination.
- **Change page type**: saves only the classification, updates the survey/type heading immediately, and marks the page as awaiting transcription. Existing content remains visible. No model selection or paid call occurs here.
- **Transcribe** beside Export: available on every page, including pages of the same type with saved reviews. Opens the shared model/provider/effort controls and queues one page. Successful replacement archives the previous page metadata, fields, flags and edits in `page_versions`, then resets the new fields' review status. History shows saved field reviews, moves and expandable snapshots in a read-only table.

Pending reviews must be saved or discarded before either action. A running transcription prevents duplicate jobs and page moves. If the page revision changes during transcription, its content is left untouched and the job fails with a retry message. Failed model calls also preserve old content. A page type must have a transcription template; Other currently has no template, so choose a supported type before transcribing it.


## Run

Restart the backend with `uv run app` from the repository root. Startup applies migrations 003 and 004 (move audit, page history and transcription state) and starts the worker. Start the frontend with `npm --prefix frontend run dev`. No database changes are applied by merely editing these source files.

## Checks

```sh
uv run pytest tests/unit/test_page_moves.py tests/unit/test_page_types.py tests/integration/test_migrations.py
npm --prefix tests run test:e2e -- page-actions.spec.ts
```

## Limits

This implementation preserves existing flags when moving; it does not rerun the pipeline's grouping checks. Review cross-page inconsistencies in both surveys after moving. The original pipeline grouping algorithm should not be rerun blindly because it would overwrite a reviewer's manual assignment.


## Database

Normal startup uses `backend/db/wilfprestsurvey.db`. Output follows `OUTPUT` in `.env` (default: `output`), and the frontend connects to port 8000. Use `uv run api` for the API alone, or `uv run app` for the API and transcription worker. Start the frontend with `npm --prefix frontend run dev`.
