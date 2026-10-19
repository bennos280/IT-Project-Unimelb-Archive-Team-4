# Development notes

See the [main README](README.md) for setup and everyday use. Run all commands below from the project root.

## Tests

| Suite | Command | Scope |
| --- | --- | --- |
| Backend unit | `uv run pytest tests/unit` | Individual pipeline, API, database, worker and validation behaviours |
| Backend integration | `uv run pytest tests/integration` | Integration checks in the backend test suite |
| Backend end-to-end | `uv run pytest tests/e2e` | A queued PDF through the API, worker, pipeline, loader and migrated database |
| Frontend unit | `npm --prefix tests run test:unit` | API adapter and export handling with mocked responses |
| Browser integration | `npm --prefix tests run test:e2e` | Frontend browser checks |
| Backend adapter integration | `npm --prefix tests run test:integration` | The frontend adapter against the backend and database |

Install the frontend and test dependencies and Chromium as described in the main README before running frontend tests. `npm --prefix tests run test:all` runs frontend lint, build and tests together. Lint and build can also be run separately with `npm --prefix frontend run lint` and `npm --prefix frontend run build`.

### Coverage and boundaries

- **Pipeline:** image preprocessing, page classification and confidence gates, fingerprints, transcription providers and settings, and input/output handling.
- **API and storage:** schema and loading, jobs, uploads, page types, transcription, review history, instructions and exports.
- **Validation:** cross-page comparisons, missing values, codebook domains, historical coding conventions and template-field compatibility. These tests use sample readings without model calls.
- **Frontend services:** request construction, response handling, errors and preservation of saved export values. Mocked unit tests are separate from adapter integration tests.

The E2E job test uses real API, worker, split, group, loader and migration-built database components. Page sorting and the paid transcription call are faked. It checks job completion, survey order, returned readings, served scan images and rejection of an already-loaded bundle. Passing it does not verify real model quality or account configuration.

Test functions remain the detailed specification; this guide groups coverage instead of duplicating a row for every test. CI configuration is in `.github/workflows/tests.yml` and runs on pull requests and pushes to `main`.

### Manual check with the real model

Use this before a demo or after pipeline changes. It uses the configured transcription account and may incur usage charges.

1. Start `uv run app` and confirm the transcription provider, model and effort have been selected in Settings.
2. Open http://127.0.0.1:8000/docs. Use `GET /bundles` to find a bundle that is not loaded, then queue its listed `pdf` with `POST /jobs`.
3. Check `GET /bundles` for job progress (`step`, `donePages`, `totalPages`) and confirm that the bundle becomes loaded with surveys.
4. Open `http://127.0.0.1:8000/survey/<survey-id>` for a returned survey and check its page readings and scan images against the source.
5. To check interruption recovery, stop the app during a run, restart it and queue the bundle again. The stopped job is marked failed; unchanged, already-transcribed pages should be reused.

## Survey consistency checks

Validation runs after survey grouping. It compares the main form (page 1) with the coded card (page 3), checks internal relationships and checks codes against `backend/db/data_dict.json`. It does not alter either reading or decide which conflicting value is correct.

### Configuration

Files are under `backend/pipeline/validate/`:

| File | Purpose |
| --- | --- |
| `checks.json` | Enables or suppresses the output of each named check |
| `conventions.json` | Determines which historical coding conventions are accepted |
| `validator.py` / `codebook.py` | Comparison rules and codebook checks |
| `run_validation.py` | `validate_survey(main, coded)` entry point |
| `pipeline_step.py` | Pipeline integration and standalone revalidation |

`checks.json` uses `true` to retain a check's flags and `false` to drop them. The documented enabled set is `dwelling_number`, `industry_code`, `occupation_code`, `municipality`, `card_living_plus_dead_is_total` and `codebook_codes`; other checks are disabled. Check the configuration file for the active values when changing rules. Supported checks are not necessarily enabled checks.

`conventions.json` uses `true` to accept a convention and `false` to treat the corresponding discrepancy as a conflict. Both configuration files must name every supported key with a Boolean value. The Python entry point also accepts `checks=` and `conventions=` overrides.

### Rule groups

| Group | Comparisons and interpretation |
| --- | --- |
| Identifiers and codes | Dwelling numbers, explicit industry/occupation codes and municipality names against codebook mappings; no prose-to-code guessing |
| Rooms and sleepouts | Bedrooms, living rooms, rooms not in daily use, sleepout counts/categories and room totals; `rooms_shared` is a category, not a count |
| Residents and children | Resident counts, age bands, sex-dependent counts, head age, boarders and living/away children; unknown sex is not guessed |
| Ages and residence | House age and residence length, including ranges and special codes rather than treating every code as an exact number |
| Internal totals | Living plus dead children, resident age-band sums, breadwinners and other subsets against residents, room totals and page 1 room contradictions |
| Codebook | Permitted codes, ranges and municipality mappings |

Leading zeros and equivalent numeric forms are normalised (`01`, `1`, `1.0`). Dwelling-number suffixes remain significant (`024 a` matches `24A`, not `24B`). Zero is a value; `none`, `nil`, `no` and `zero` count as zero. Blank resident-template columns are not counted as residents.

### Historical coding conventions

These are the documented defaults; the configuration file controls the active values.

| Key | Default | Accepted interpretation when enabled |
| --- | --- | --- |
| `kitchen_not_a_living_room` | `false` | One fewer coded living room when the coded total accounts for the kitchen separately |
| `sleepout_counted_as_bedroom` | `true` | Sleepouts included in coded bedrooms and then coded as zero sleepouts |
| `serving_residents_left_out` | `true` | Residents serving in the forces omitted from resident/over-10 totals and counted as children away |
| `ten_year_olds_over_10` | `true` | Ten-year-olds counted in the over-10 group instead of the 5–10 group |
| `another_resident_as_head` | `true` | Another resident of the coded head's sex supplies the head age |
| `part_years_dropped` | `true` | Part years dropped or rounded up |
| `suburb_coded_as_council` | `true` | A suburb coded to a council; a different named council still conflicts |
| `zero_rooms_means_none` | `true` | Room code zero means none as well as over eleven |

### Outputs and limitations

`validation/output_flagged.json` in the run folder records the issue type, reason, involved fields and comparison details. `review.json` receives a short entry for each flagged page. The loader stores conflicts as field flags for browser review.

- Conflict types distinguish page 1–3, page 1 internal, page 3 internal and page 3 codebook conflicts.
- A missing, `/`, `[?]` or unparseable counterpart produces an incomplete comparison; only conflicts become database flags. If both corresponding values are blank, the comparison is skipped.
- Surveys without exactly one main form and one coded card, or with a coded reading lacking `number_of_dwelling`, appear under `not_validated`.
- Page 1 `other_children` is free text and is not counted; its presence generates a warning. Children checks assume one family per survey.
- Industry/occupation prose is not mapped to codes. Structural material and tenure are not compared.

To revalidate an existing run without transcribing pages again:

```sh
uv run survey validate <run>/manifest.json
```

Rules use the field names in `backend/pipeline/transcribe/templates/`. When changing templates or rules, run the validation tests, including `tests/unit/test_validate_fields.py`, which detects rule/template mismatches.

## Maintenance

| Task | Entry point |
| --- | --- |
| Start components separately | `uv run api` (reloads on save) or `uv run worker` |
| Retrain page classification | Add labelled pages under `tests/identify/pages/<label>/`, then run `uv run survey train`; foreign forms use `other/` |
| Change database tables | Update `backend/db/models.py`, then run `uv run alembic revision --autogenerate -m "what changed"` and review the generated migration |
| Add a pipeline step | Add a function and `STEPS` entry in `backend/pipeline/run.py`; keep substantial implementation in its pipeline module |

Pipeline steps read and write `run.pages` and use `run.flag(page, step, reason)` for review issues. Keep expensive module imports inside the step function.

Interrupted CLI runs reuse saved transcripts only while the image, page type, provider/model settings, prompt, template and stored result still match. Passing a completed PDF explicitly reruns it; its generated page folder is replaced after successful rendering so obsolete pages do not remain.
