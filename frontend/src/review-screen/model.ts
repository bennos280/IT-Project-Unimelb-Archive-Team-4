// Defines possible survey card/page types shown in the review screen.
export type PageType = string;

// Represents a validation flag attached to a particular extracted field.
// Flags are used to tell the reviewer why a field may need attention.

export type Flag = {
  id: string;
  fieldId: string;
  kind:
    | "inconsistency"
    | "gibberish"
    | "uncertain"
    | "between_page_mismatch"
    | "total_mismatch"
    | "count_exceeds_total";
  reason: string;
};

// Stores a field region as fractions of the full image dimensions (0–1).
// The current viewer reads shared regions from fieldLocations.ts.
export type SourceRegion = {
  x: number;
  y: number;
  width: number;
  height: number;
};

// Represents one extracted survey field shown in the review panel.
export type Field = {
  sourceRegion?: SourceRegion;
  id: string;
  label: string;
  group: string;
  value: string | null;
};

// Represents one page of a survey, including its source image,
// extracted fields, and any validation flags.
export type SurveyPage = {
  id: string;
  type: PageType;
  needsTranscription?: boolean;
  imageUrl: string;
  fields: Field[];
  flags: Flag[];
};

// Represents the complete survey loaded by the review screen.
export type Survey = {
  id: string;
  title: string;
  pages: SurveyPage[];
};

// Validate survey identity, pages, unique field IDs and flags before rendering backend data.
export function parseSurvey(input: unknown, expectedId: string): Survey {
  const s = input as Survey;
  if (
    !s ||
    s.id !== expectedId ||
    !s.title ||
    !Array.isArray(s.pages) ||
    !s.pages.length
  )
    throw new Error(
      "Survey response is missing data or belongs to another survey.",
    );
  const ids = new Set<string>();
  for (const p of s.pages) {
    if (
      !p.id ||
      ids.has(p.id) ||
      typeof p.type !== "string" ||
      !p.type.trim() ||
      typeof p.imageUrl !== "string" ||
      !/^(https?:\/\/|\/[^/])/.test(p.imageUrl) ||
      !Array.isArray(p.fields) ||
      !Array.isArray(p.flags)
    )
      throw new Error("Invalid or duplicate survey page.");
    ids.add(p.id);
    const fields = new Set<string>();
    for (const f of p.fields) {
      if (
        !f.id ||
        fields.has(f.id) ||
        typeof f.label !== "string" ||
        typeof f.group !== "string" ||
        !(f.value === null || typeof f.value === "string")
      )
        throw new Error("Invalid field or label.");
      fields.add(f.id);
    }
    for (const f of p.flags)
      if (
        !f.id ||
        !fields.has(f.fieldId) ||
        typeof f.reason !== "string" ||
        ![
          "inconsistency",
          "gibberish",
          "uncertain",
          "between_page_mismatch",
          "total_mismatch",
          "count_exceeds_total",
        ].includes(f.kind)
      )
        throw new Error("Flag does not match a field on this page.");
  }
  return s;
}

// Maps page types to headings displayed in the UI.
const pageNames: Record<string, string> = {
  main: "Main page",
  notes: "Notes page",
  coded: "Coded page",
  other: "Other page",
};
// Notes and other pages hold one free-text field.
export function isTextPage(type: PageType): boolean {
  return type === "notes" || type === "other";
}
export function getPageName(type: PageType): string {
  return Object.hasOwn(pageNames, type) ? pageNames[type] : type;
}
