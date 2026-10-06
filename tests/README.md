# Test suite for the Wilfred Prest survey pipeline

**206 tests runs in ~160s.**

```bash
uv run pytest tests
```

split into 3 categories: Unit, Integration and e2e tests.
See README in each folder for a more comprehensive list of tests.

## US7 frontend tests

US7 tests are now grouped with the repository tests:

- `unit/ui-reviewscreen/api.test.ts`: Vitest adapter tests with mocked responses.
- `e2e/ui-reviewscreen/review.spec.ts`: Playwright UI tests with an isolated mock API.
- `integration/ui-reviewscreen/us7-8-check.py` and `.mjs`: real adapter/FastAPI checks using temporary SQLite data; no live database writes.

From the repository root:

```bash
npm --prefix frontend ci
npm --prefix tests ci
cd tests
npx playwright install chromium
npm run test:unit
npm run test:e2e
npm run test:e2e:ui
uv run --with httpx2 python integration/ui-reviewscreen/us7-8-check.py
```

The integration runner needs backend Python dependencies and FastAPI TestClient's HTTP client (httpx2 with the currently installed version). It does not test the Vite proxy, images or real networking. It seeds from frontend demo JSON and reports child numbering mismatches rather than hiding them.

After setup, unit/browser commands also work from frontend via `npm run test:unit`, `npm run test:e2e`, and `npm run test:e2e:ui`. Tests are separate from the frontend production build. Pytest continues to discover the existing Python test files, not these TypeScript tests. Test expectations have been preserved during the move; failures may expose differences from the current adapter.
