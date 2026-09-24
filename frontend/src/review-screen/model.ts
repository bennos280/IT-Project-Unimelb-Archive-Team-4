export type PageType = "main" | "notes" | "coded";
export type Flag = {
  id: string;
  fieldId: string;
  kind: "inconsistency" | "gibberish" | "uncertain";
  reason: string;
};
export type SourceRegion = { x: number; y: number; width: number; height: number };
export type Field = {
  sourceRegion?: SourceRegion;
  id: string;
  label: string;
  group: string;
  value: string | null;
};
export type SurveyPage = {
  id: string;
  type: PageType;
  imageUrl: string;
  fields: Field[];
  flags: Flag[];
};
export type Survey = {
  id: string;
  title: string;
  pages: SurveyPage[];
};
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
      !["main", "notes", "coded"].includes(p.type) ||
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
        !["inconsistency", "gibberish", "uncertain"].includes(f.kind)
      )
        throw new Error("Flag does not match a field on this page.");
  }
  return s;
}
export const pageNames = {
  main: "Main page",
  notes: "Notes page",
  coded: "Coded page",
};
