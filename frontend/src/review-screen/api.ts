// Connects the US7 review screen to the backend.
import { parseSurvey } from "./model";

const API_BASE = "/api";

export type Reviewer = {
  id: number;
  name: string;
};

type BackendReviewer = {
  id: number;
  name: string;
};

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

type Changes = Record<
  string,
  {
    value: string | null;
    reviewerId: number;
  }
>;

type SaveResult = {
  revision: number;
  savedAt: string;
};

type SurveyResponse = {
  id: string;
  title: string;
  pages: Array<{
    id: string;
    type: string;
    imageUrl?: string | null;
    fields: unknown[];
    flags?: Array<{
      id?: string;
      fieldId: string;
      kind: string;
      reason?: string;
    }> | null;
  }>;
};

// Send a request and display errors into message the review screen can display
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, options);

  if (!response.ok) {
    let message = `Request failed (${response.status}).`;

    try {
      const body = await response.json();

      if (typeof body.detail === "string") {
        message = body.detail;
      } else if (Array.isArray(body.detail)) {
        message = body.detail
          .map(
            (error: { loc?: Array<string | number>; msg?: string }) =>
              `${error.loc?.join(".") || "Request"}: ${
                error.msg || "Invalid value"
              }`,
          )
          .join("; ");
      }
    } catch {
      // Keep the default message if the response is not JSON.
    }

    throw new Error(message);
  }

  return (await response.json()) as T;
}

// Load extracted fields and adapt flags and image fallbacks, then validate the response
export async function getSurvey(id: string, signal?: AbortSignal) {
  const data = await request<SurveyResponse>(
    `/survey/${encodeURIComponent(id)}`,
    { signal },
  );

  if (Array.isArray(data?.pages)) {
    for (const page of data.pages) {
      page.flags = (page.flags ?? []).map((flag, index) => ({
        ...flag,
        id: flag.id || `${page.id}:${flag.fieldId}:${index}`,
        reason: flag.reason?.trim() || "No reason was supplied for this flag.",
      }));

      // Allows data to load while image serving is not connected.
      if (
        typeof page.imageUrl !== "string" ||
        !/^(https?:\/\/|\/[^/])/.test(page.imageUrl)
      ) {
        page.imageUrl = "/image-not-connected";
      }
    }
  }

  return parseSurvey(data, id);
}

// Load reviewers using the IDs returned by the backend.
export async function getReviewers(): Promise<Reviewer[]> {
  const people = await request<BackendReviewer[]>("/reviewers");

  return people.map((person) => ({
    id: person.id,
    name: person.name,
  }));
}

// Trim the name, reuse an existing reviewer or create one through backend.
export async function createReviewer(name: string): Promise<Reviewer> {
  const clean = name.trim();

  if (!clean) {
    throw new Error("Enter a reviewer name.");
  }

  const people = await getReviewers();
  const existing = people.find((person) => person.name === clean);

  if (existing) {
    return existing;
  }

  // The backend assigns the new reviewer ID.

  const person = await request<BackendReviewer>("/reviewers", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name: clean }),
  });

  return {
    id: person.id,
    name: person.name,
  };
}

// Load the latest saved corrections and page revisions numbers for a survey
export async function getReviews(id: string): Promise<Stored> {
  return request<Stored>(`/reviews/${encodeURIComponent(id)}`);
}

// Validate pending reviews and submit one page with its proposed next revision
export async function saveReviews(
  id: string,
  pageId: string,
  revision: number,
  changes: Changes,
): Promise<SaveResult> {
  if (Object.keys(changes).length === 0) {
    throw new Error("There are no unsaved reviews on this page.");
  }

  const [survey, people] = await Promise.all([getSurvey(id), getReviewers()]);

  const page = survey.pages.find((item) => item.id === pageId);

  if (!page) {
    throw new Error("Page not found.");
  }

  const pageReviews: Record<string, Review> = {};

  for (const [fieldId, edit] of Object.entries(changes)) {
    const field = page.fields.find((item) => item.id === fieldId);
    const person = people.find((item) => item.id === edit.reviewerId);

    if (!field) {
      throw new Error(
        `Could not save: field "${fieldId}" was not found on this page.`,
      );
    }

    if (!person) {
      throw new Error("Unknown reviewer. Select a registered reviewer.");
    }

    // Preserve null values when sending reviews to db
    // If the backend rejects the save, the UI keeps the changes unsaved.

    pageReviews[fieldId] = {
      value: edit.value,
      original: field.value,
      reviewer: person.name,
      reviewerId: person.id,
      savedAt: "",
    };
  }

  return request<SaveResult>(`/reviews/${encodeURIComponent(id)}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      reviews: {
        [pageId]: pageReviews,
      },
      revisions: {
        [pageId]: revision + 1,
      },
    }),
  });
}
