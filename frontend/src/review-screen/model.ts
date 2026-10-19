import type { ArchiveItem } from "../progress/backend";
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
    | "invalid"
    | "check"
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
  // Where the transcription saw a field with no fixed place, such as an annotation.
  location?: string | null;
  // The named part of the card an annotation is in, and its label; sourceRegion is that part's box.
  area?: string | null;
  areaLabel?: string | null;
};

// Represents one page of a survey, including its source image,
// extracted fields, and any validation flags.
export type SurveyPage = {
  id: string;
  type: PageType;
  typeLabel?: string;
  needsTranscription?: boolean;
  imageUrl: string;
  fields: Field[];
  flags: Flag[];
};

// Represents the complete survey loaded by the review screen.
export type Survey = {
  bundleId?: string;
  item?: { name: string; archive: ArchiveItem | null }; // the item the record belongs to
  collectionId?: number;
  id: string;
  title: string;
  recordName: string; // what the collection calls a record
  grouped: boolean; // whether the collection's pages group into records
  wholeItem?: boolean; // the record is its whole item, all the item's pages
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
      "The record's data is missing or belongs to another record.",
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
      throw new Error("Invalid or duplicate page.");
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
          "invalid",
          "check",
          "between_page_mismatch",
          "total_mismatch",
          "count_exceeds_total",
        ].includes(f.kind)
      )
        throw new Error("Flag does not match a field on this page.");
  }
  return s;
}

// A page of free writing: its writing is the field "text" (its annotations are fields too).
export function isTextPage(page: SurveyPage): boolean {
  return page.fields.some((field) => field.id === "text");
}
// The page type's label from the db, else its name.
export function getPageName(page: SurveyPage): string {
  return page.typeLabel ?? page.type;
}
