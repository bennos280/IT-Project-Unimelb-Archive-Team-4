// Frontend-only adapter. Replace these functions with API requests later.
import { parseSurvey } from "./model";
export type Reviewer = { id: number; name: string };
type Review = {
  value: string | null;
  original: string | null;
  reviewer: string;
  reviewerId: number;
  savedAt: string;
};
type Stored = {
  reviews: Record<string, Record<string, Review>>;
  revisions: Record<string, number>;
};
const key = (id: string) => `us7-standalone:${id}`;
export async function getSurvey(id: string, signal?: AbortSignal) {
  const response = await fetch("/us7-demo/survey.json", { signal });
  if (!response.ok)
    throw new Error("Copy public/us7-demo into your frontend/public folder.");
  return parseSurvey(await response.json(), id);
}
export async function getReviewers(): Promise<Reviewer[]> {
  return JSON.parse(localStorage.getItem("us7-standalone-reviewers") || "[]");
}
export async function createReviewer(name: string): Promise<Reviewer> {
  const people = await getReviewers();
  const clean = name.trim();
  if (!clean) throw new Error("Enter a reviewer name.");
  const existing = people.find((p) => p.name === clean);
  if (existing) return existing;
  const person = {
    id: Math.max(0, ...people.map((p) => p.id)) + 1,
    name: clean,
  };
  localStorage.setItem(
    "us7-standalone-reviewers",
    JSON.stringify([...people, person]),
  );
  return person;
}
export async function getReviews(id: string): Promise<Stored> {
  return JSON.parse(
    localStorage.getItem(key(id)) || '{"reviews":{},"revisions":{}}',
  );
}
export async function saveReviews(
  id: string,
  pageId: string,
  revision: number,
  changes: Record<string, { value: string | null; reviewerId: number }>,
) {
  const data = await getReviews(id);
  if ((data.revisions[pageId] || 0) !== revision)
    throw new Error(
      "This page changed in another tab. Export your draft, then reload.",
    );
  const survey = await getSurvey(id);
  const page = survey.pages.find((p) => p.id === pageId);
  if (!page) throw new Error("Page not found.");
  const people = await getReviewers();
  const savedAt = new Date().toISOString();
  const saved = { ...data.reviews[pageId] };
  for (const [fieldId, edit] of Object.entries(changes)) {
    const field = page.fields.find((f) => f.id === fieldId);
    const person = people.find((p) => p.id === edit.reviewerId);
    if (!field || !person) throw new Error("Unknown field or reviewer.");
    saved[fieldId] = {
      ...edit,
      original: field.value,
      reviewer: person.name,
      savedAt,
    };
  }
  data.reviews[pageId] = saved;
  data.revisions[pageId] = revision + 1;
  localStorage.setItem(key(id), JSON.stringify(data));
  return { revision: revision + 1, savedAt };
}
