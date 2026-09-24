# US7 — Survey Review Screen

US7 provides a review interface for comparing extracted survey data with the original scanned card. Reviewers can inspect flagged values, make corrections, and record which fields they have checked.

## Features

- Display the source scan and extracted fields side by side.
- Navigate between main, notes, and coded pages.
- Zoom, pan, fit the image to the viewer, and enter fullscreen.
- Click a mapped field to highlight its location on the scan.
- Search fields and filter fields that need checking.
- Display flags and their reasons.
- Select or add a reviewer.
- Edit individual values or mark all fields on a page as reviewed.
- Save reviews in browser storage.

## Run locally

From the repository root:

```sh
cd frontend
npm ci
npm run dev
```

Open the Local URL printed in the terminal. Keep the terminal running while using the app.

## Review a survey

1. Open the survey and select a page using the navigation arrows.
2. Compare the extracted values with the source scan.
3. Expand **Needs checking** to read a flag’s reason.
4. Select or add your reviewer name.
5. Click the pencil beside a field to correct or review its value.
6. Select **Apply review**.
7. Click **Save Page Transcript** to persist your changes.

Applying a review creates an unsaved change. Saving the page stores it in the current browser. Reviewing a field does not automatically remove its flags.

## Field locations

`fieldLocations.ts` stores shared image regions for each page layout, keyed by page type and field ID.

Main and coded pages use these regions to locate fields. Coordinates are fractions of the full image dimensions, so the same map can be reused for consistently aligned scans.

Scans with different cropping, rotation, or layouts may require different mappings.

## Main files

| File                                    | Purpose                                                   |
| --------------------------------------- | --------------------------------------------------------- |
| `src/App.tsx`                           | Connects the review session to the review screen          |
| `src/review-screen/ReviewScreen.tsx`    | Displays fields, flags, navigation, and review controls   |
| `src/review-screen/ImageViewer.tsx`     | Handles scan display, zoom, pan, and highlighting         |
| `src/review-screen/useReviewSession.ts` | Manages loading, navigation, and review state             |
| `src/review-screen/api.ts`              | Loads sample data and persists reviews in browser storage |
| `src/review-screen/model.ts`            | Defines and validates survey data                         |
| `src/review-screen/fieldLocations.ts`   | Defines shared field locations                            |
| `src/review-screen/review.css`          | Styles the review screen                                  |
| `src/review-screen/base.css`            | Defines shared base styles                                |
| `public/us7-demo/`                      | Contains sample survey data and scans                     |

## Data and storage

The current adapter loads `public/us7-demo/survey.json`. Each page includes an ID, page type, source image URL, labelled fields, and flags.

Reviewer names and saved reviews are stored using browser `localStorage`. They are specific to the browser and site address and are not shared between users. Clearing browser storage removes them.

The US8 database connection is not implemented in this adapter.

## Code checks

From the `frontend` folder:

```sh
npm run lint
npm run build
```

Lint checks code rules. The build checks TypeScript and produces the website files in `dist`.

## Manual testing

- Confirm each page displays its matching scan and extracted values.
- Navigate through main, notes, and coded pages.
- Check zoom, pan, fit-to-page, and fullscreen controls.
- Click mapped fields and verify their highlighted locations.
- Search and filter fields, including searches with no results.
- Expand flags and check their reasons.
- Save a correction, refresh the page, and confirm it remains.
- Confirm blank values and transcription markers such as `/` and `[?]` remain distinguishable.
- Confirm readability and usability with Lachlan.

## Remaining integration work

- Replace the demo adapter with backend API requests.
- Load real survey groupings, scans, labels, and flags from US8.
- Persist reviewers and corrections in the shared database.
- Verify image-to-data matching with real records.
- Complete usability testing with Lachlan.

US12 export functionality is developed separately and is available only when its changes are integrated into the current branch.
