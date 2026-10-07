Currently UI uses us7-demo.sqlite using seed_demo.py, which survey `216417` and its main, notes, and coded pages. It refuses to overwrite an existing database.

Skip seeding if you already have a populated demo database. The database connection in `backend/database.py` must point to that file.

The seed stores image paths, not image files. Keep the corresponding demo scans in `frontend/public/us7-demo/`.

# US7 — Survey Review Screen

US7 provides a review interface for comparing extracted survey data with the original scanned card. Reviewers can inspect flagged values, make corrections, and record which fields they have checked.

## Features

- Display source scans and extracted fields side by side.
- Navigate between main, notes, and coded pages.
- Zoom, pan, fit the image to the viewer, and enter fullscreen.
- Click a mapped field to highlight its location on the scan.
- Search fields and filter fields that need checking.
- Display flags and available explanations.
- Select or add a reviewer.
- Edit individual values or mark all fields on a page as reviewed.
- Save reviews through the US8 backend to SQLite.

## First-time setup

Requirements: Python 3.12 or newer, uv, npm, and a Node.js version compatible with the project's Vite version(i.e. Node.js 24.x )

From the repository root:

```sh
uv sync
```

## Run locally

Start the backend from the repository root:

```sh
uv run uvicorn backend.main:app --reload --port 8000
```

In a second terminal, start the frontend:

```sh
cd frontend
npm ci
npm run dev -- --port 5174 --strictPort
```

Open:

```text
http://localhost:5174/survey=216417_1
```

Keep both terminals running while using the app.

The Vite development server forwards `/api` requests to US8 on port `8000`. Production hosting will need an equivalent API configuration.

## Review a survey

1. Open the survey and select a page using the navigation arrows.
2. Compare the extracted values with the source scan.
3. Expand **Needs checking** to read the available flag explanation.
4. Select or add your reviewer name.
5. Click the pencil beside a field to correct or review its value.
6. Select **Apply review**.
7. Click **Save Page Transcript** to persist your changes.

Applying a review creates an unsaved change. Saving sends the pending reviews for the current page to US8; it does not save all three pages at once.

Reviewing a field does not automatically remove its flags. If saving fails, the pending changes remain unsaved and an error is displayed.

## Field locations

`fieldLocations.ts` stores shared image regions for each page layout, keyed by page type and field ID.

Main and coded pages use these regions to locate fields. Coordinates are fractions of the full image dimensions, allowing the same map to be reused for consistently aligned scans. Notes are reviewed as a whole page.

Scans with different cropping, rotation, or layouts may require different mappings.

## Main files

| File                                    | Purpose                                                 |
| --------------------------------------- | ------------------------------------------------------- |
| `src/App.tsx`                           | Connects the review session to the review screen        |
| `src/review-screen/ReviewScreen.tsx`    | Displays fields, flags, navigation, and review controls |
| `src/review-screen/ImageViewer.tsx`     | Handles scan display, zoom, pan, and highlighting       |
| `src/review-screen/useReviewSession.ts` | Manages loading, drafts, navigation, and saving         |
| `src/review-screen/api.ts`              | Connects US7 to the US8 API                             |
| `src/review-screen/model.ts`            | Defines and validates survey data                       |
| `src/review-screen/fieldLocations.ts`   | Defines shared field locations                          |
| `src/review-screen/review.css`          | Styles the review screen                                |
| `src/review-screen/base.css`            | Defines shared base styles                              |
| `vite.config.ts`                        | Configures the development API proxy                    |
| `public/us7-demo/`                      | Contains demo survey JSON and scan images               |
| `../backend/seed_demo.py`               | Creates the demo SQLite database                        |
| `../backend/seed_demo.sql`              | Defines the demo schema and inserts sample values       |

## Data and storage

The frontend loads survey data from the SQLite database through the US8 API.

Each page includes its ID, page type, image URL, labelled fields, and flags. Reviewer names and saved corrections are loaded from the backend.

Unsaved changes are held in frontend memory. Successfully saved reviews are stored in SQLite and remain available after refreshing the browser.

Some existing UI messages still mention browser storage; those messages need updating to reflect the backend connection.

`getReviews()` returns the latest saved review for each field, grouped by page ID and field ID, together with page revision numbers. Each successful page save increments its revision to help detect outdated saves.

## Code checks

From the `frontend` folder:

```sh
npm run lint
npm run build
```

Lint checks code rules. The build checks TypeScript and produces website files in `dist`.

## Manual testing

- Confirm each page displays its matching scan and extracted values.
- Navigate through main, notes, and coded pages.
- Check zoom, pan, fit-to-page, and fullscreen controls.
- Click mapped fields and verify their highlighted locations.
- Search and filter fields, including searches with no results.
- Expand flags and check their explanations.
- Save a correction, refresh, and confirm it remains.
