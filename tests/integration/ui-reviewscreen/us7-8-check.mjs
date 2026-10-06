// Runs the real frontend adapter; Python bridges fetch calls into FastAPI TestClient.
import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import readline from "node:readline";
const [frontend, fixturePath] = process.argv.slice(2);
const require = createRequire(import.meta.url);
const ts = require(
  path.join(frontend, "node_modules/typescript/lib/typescript.js"),
);
const fixture = JSON.parse(fs.readFileSync(fixturePath, "utf8"));
const pending = new Map();
let sequence = 0;
const lines = readline.createInterface({ input: process.stdin });

// Matches each response from the Python bridge to its pending fetch
// request and resolves it as a standard Response object.
lines.on("line", (line) => {
  const message = JSON.parse(line);
  const resolve = pending.get(message.id);
  if (resolve) {
    pending.delete(message.id);
    resolve(
      new Response(message.body, {
        status: message.status,
        headers: { "Content-Type": "application/json" },
      }),
    );
  }
});

// Sends frontend fetch requests to Python over standard output.
// Python calls FastAPI TestClient and returns the response on stdin.
globalThis.fetch = async (url, options = {}) => {
  const id = ++sequence;
  const promise = new Promise((resolve) => pending.set(id, resolve));
  process.stdout.write(
    JSON.stringify({
      type: "request",
      id,
      url: String(url),
      method: options.method || "GET",
      body: options.body,
    }) + "\n",
  );
  return promise;
};
const directory = path.join(frontend, "src/review-screen");

// Converts TypeScript into executable JavaScript and returns an
// importable data URL. This transpiles code but does not type-check it.
function compile(source) {
  const { outputText } = ts.transpileModule(source, {
    compilerOptions: {
      target: ts.ScriptTarget.ES2022,
      module: ts.ModuleKind.ES2022,
    },
  });
  return (
    "data:text/javascript;base64," + Buffer.from(outputText).toString("base64")
  );
}
const modelURL = compile(
  fs.readFileSync(path.join(directory, "model.ts"), "utf8"),
);
const apiSource = fs
  .readFileSync(path.join(directory, "api.ts"), "utf8")
  .replace(/(["'])\.\/model\1/g, JSON.stringify(modelURL));
const api = await import(compile(apiSource));
const results = [];

// Throws a failure when an expected condition is not met.

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

// Records each check as PASS or FAIL and continues to later checks.
async function test(name, fn) {
  try {
    await fn();
    results.push({ name, status: "PASS" });
  } catch (error) {
    results.push({ name, status: "FAIL", reason: error.message });
  }
}
const main = fixture.pages.find((p) => p.type === "main");
const notes = fixture.pages.find((p) => p.type === "notes");
const ordinary = main.fields.find((f) => f.id === "address");
const reviewer = fixture.reviewer;

// Checks survey page count, page types, and non-child field IDs and
// values through the real adapter and backend. Children are checked next.
await test("Load demo survey through actual US7 getSurvey and parseSurvey", async () => {
  const survey = await api.getSurvey(fixture.id);
  assert(survey.pages.length === fixture.pages.length, "Page count differs");
  for (const source of fixture.pages) {
    const page = survey.pages.find((p) => p.id === source.id);
    assert(
      page?.type === source.type,
      `Missing or mismatched page ${source.id}`,
    );
    assert(
      page.imageUrl === source.imageUrl,
      `Wrong image URL for ${source.id}`,
    );
    assert(
      page.fields.length === source.fields.length,
      `Field count differs for ${source.id}`,
    );
    for (const field of source.fields.filter(
      (f) => !f.id.startsWith("other_children."),
    )) {
      const returned = page.fields.find((f) => f.id === field.id);
      assert(
        returned && returned.value === field.value,
        `Missing/wrong field ${source.id}: ${field.id}`,
      );
    }
  }
});
// Checks that US8 returns the child IDs defined in the SQL seed.
// Child numbers are unique across the page, not within each residence group.
await test("Child field IDs returned by US8 match SQL seed", async () => {
  const survey = await api.getSurvey(fixture.id);
  const page = survey.pages.find((p) => p.id === main.id);

  assert(page, `Main page ${main.id} was not returned`);

  const expectedIds = main.fields
    .filter((field) => field.id.startsWith("other_children."))
    .map((field) => field.id);

  const returnedIds = page.fields
    .filter((field) => field.id.startsWith("other_children."))
    .map((field) => field.id)
    .sort();

  assert(
    JSON.stringify(returnedIds) === JSON.stringify([...expectedIds].sort()),
    `Child IDs differ. Expected: ${expectedIds.join(", ")}; returned: ${returnedIds.join(", ")}`,
  );
});

// Checks that the seeded backend reviewer is returned with the
// frontend's expected id and name.
await test("Reviewer list converts reviewer_id to id", async () => {
  assert(
    (await api.getReviewers()).some(
      (r) => r.id === reviewer.id && r.name === reviewer.name,
    ),
    "Seeded reviewer not returned correctly",
  );
});

// Creates a reviewer through the real adapter and confirms that the
// backend returns that reviewer in a subsequent list request.
await test("Create a reviewer through current frontend request", async () => {
  const created = await api.createReviewer("Integration created reviewer");
  assert(Number.isInteger(created.id), "Invalid reviewer ID");
  assert(
    (await api.getReviewers()).some(
      (r) => r.id === created.id && r.name === created.name,
    ),
    "Reviewer did not persist",
  );
});

// Saves one correction using the latest page revision, then reloads
// reviews and checks its value, reviewer ID, timestamp, and revision.
async function saveAndReload(page, field, value) {
  assert(
    page && field,
    "SQL seed is missing the page or field required by this check",
  );
  const before = await api.getReviews(fixture.id);
  const revision = before.revisions[page.id] ?? 0;
  const saved = await api.saveReviews(fixture.id, page.id, revision, {
    [field.id]: { value, reviewerId: reviewer.id },
  });
  assert(
    saved.revision === revision + 1 && saved.savedAt,
    "Invalid revision or timestamp",
  );
  const after = await api.getReviews(fixture.id);
  const review = after.reviews[page.id]?.[field.id];
  assert(review, `Saved review missing after reload: ${field.id}`);
  assert(
    review.original === field.value,
    `Wrong original value for ${field.id}`,
  );
  assert(review.value === value, `Wrong saved value for ${field.id}`);
  assert(
    review.reviewerId === reviewer.id && review.savedAt,
    "Missing reviewer/time",
  );
  assert(
    after.revisions[page.id] === saved.revision,
    "Reloaded revision differs",
  );
}

// Checks that an ordinary field correction survives a reload.
await test("Save and reload ordinary field", () =>
  saveAndReload(main, ordinary, "Integration correction 1"));

// Checks that a second correction replaces the first in returned reviews.
await test("Second correction returns latest value", () =>
  saveAndReload(main, ordinary, "Integration correction 2"));

// Checks that an outdated revision is rejected and the latest
// successful correction remains unchanged.
await test("Reject outdated save and retain latest correction", async () => {
  let rejected = false;
  try {
    await api.saveReviews(fixture.id, main.id, 0, {
      [ordinary.id]: { value: "STALE", reviewerId: reviewer.id },
    });
  } catch {
    rejected = true;
  }
  assert(rejected, "Outdated save was accepted");
  const stored = await api.getReviews(fixture.id);
  assert(
    stored.reviews[main.id]?.[ordinary.id]?.value ===
      "Integration correction 2",
    "Newer correction was overwritten or not available",
  );
});

// Checks that "/", "[?]", and null survive a real save-and-reload cycle.
for (const value of ["/", "[?]", null]) {
  await test(`Preserve marker ${JSON.stringify(value)}`, () =>
    saveAndReload(main, ordinary, value));
}
const blank = main.fields.find((f) => f.value === null && !f.id.includes("."));
// Checks correction of an ordinary field whose original value is null.
await test("Correct a field whose original value is null", () =>
  saveAndReload(main, blank, "New value"));
// Checks that the first notes field can be saved and reloaded.
await test("Save and reload notes", () =>
  saveAndReload(notes, notes?.fields[0], "Integration notes"));
const childField = main.fields.find(
  (f) =>
    f.id.startsWith("other_children.") &&
    f.id.split(".")[2] === "0" &&
    f.value !== null,
);
// Checks that the selected non-null child field can be saved and reloaded.
await test("Save and reload child field including index zero", () =>
  saveAndReload(main, childField, "Integration child"));

// Checks resident zero and resident one separately to expose backend
// conditions that mistakenly treat zero as a missing resident number.
for (const index of [0, 1]) {
  const field = main.fields.find(
    (f) => f.id.startsWith(`residents.${index}.`) && f.value !== null,
  );
  await test(`Save and reload resident ${index}`, () =>
    saveAndReload(main, field, "Integration resident"));
}

// Sends the complete results to Python for reporting.
process.stdout.write(JSON.stringify({ type: "done", results }) + "\n");
lines.close();
