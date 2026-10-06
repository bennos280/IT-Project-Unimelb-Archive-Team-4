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
function assert(condition, message) {
  if (!condition) throw new Error(message);
}
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
let reviewer = { id: 900001, name: "Seeded integration reviewer" };
await test("Load demo survey through actual US7 getSurvey and parseSurvey", async () => {
  const survey = await api.getSurvey(fixture.id);
  assert(survey.pages.length === fixture.pages.length, "Page count differs");
  for (const source of fixture.pages) {
    const page = survey.pages.find((p) => p.id === source.id);
    assert(
      page?.type === source.type,
      `Missing or mismatched page ${source.id}`,
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
await test("Child field IDs returned by US8 match demo field IDs", async () => {
  const survey = await api.getSurvey(fixture.id);
  const page = survey.pages.find((p) => p.id === main.id);
  for (const field of main.fields.filter((f) =>
    f.id.startsWith("other_children."),
  )) {
    assert(
      page.fields.some((f) => f.id === field.id),
      `Missing ID ${field.id}; returned: ${page.fields
        .filter((f) => f.id.startsWith("other_children."))
        .map((f) => f.id)
        .join(", ")}`,
    );
  }
});
await test("Reviewer list converts reviewer_id to id", async () => {
  assert(
    (await api.getReviewers()).some(
      (r) => r.id === reviewer.id && r.name === reviewer.name,
    ),
    "Seeded reviewer not returned correctly",
  );
});
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
async function saveAndReload(page, field, value) {
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
await test("Save and reload ordinary field", () =>
  saveAndReload(main, ordinary, "Integration correction 1"));
await test("Second correction returns latest value", () =>
  saveAndReload(main, ordinary, "Integration correction 2"));
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
for (const value of ["/", "[?]", null]) {
  await test(`Preserve marker ${JSON.stringify(value)}`, () =>
    saveAndReload(main, ordinary, value));
}
const blank = main.fields.find((f) => f.value === null && !f.id.includes("."));
if (blank)
  await test("Correct a field whose original value is null", () =>
    saveAndReload(main, blank, "New value"));
if (notes)
  await test("Save and reload notes", () =>
    saveAndReload(notes, notes.fields[0], "Integration notes"));
const childField = main.fields.find(
  (f) => f.id.startsWith("other_children.") && f.value !== null,
);
if (childField)
  await test("Save and reload child field including index zero", () =>
    saveAndReload(main, childField, "Integration child"));
// Resident tests run last: current US8 may save rows it cannot subsequently read.
for (const index of [0, 1]) {
  const field = main.fields.find(
    (f) => f.id.startsWith(`residents.${index}.`) && f.value !== null,
  );
  if (field)
    await test(`Save and reload resident ${index}`, () =>
      saveAndReload(main, field, "Integration resident"));
}
process.stdout.write(JSON.stringify({ type: "done", results }) + "\n");
lines.close();
