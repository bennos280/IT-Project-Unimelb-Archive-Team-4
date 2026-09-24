//Builds export records using saved corrections while preserving source references and review statuses.
import type { Survey } from "../review-screen/model";

type SavedReview = { value: string | null; savedAt?: string };
export type SavedReviews = Record<string, Record<string, SavedReview>>;

/** Export only persisted corrections; never pass the session's draft state. */
export function buildSurveyExport(survey: Survey, reviews: SavedReviews) {
  const pages = survey.pages.map((page) => ({
    pageId: page.id,
    label: page.type,
    sourceImage: page.imageUrl,
    status:
      page.fields.every((field) => reviews[page.id]?.[field.id]?.savedAt) &&
      page.fields.length > 0
        ? "Reviewed"
        : "ToBeReviewed",
    fields: page.fields.map((field) => {
      const saved = reviews[page.id]?.[field.id];
      if (
        saved?.savedAt &&
        saved.value !== null &&
        typeof saved.value !== "string"
      ) {
        throw new Error(`Saved value for ${page.id}: ${field.id} is invalid.`);
      }
      return {
        id: field.id,
        label: field.label,
        group: field.group,
        value: saved?.savedAt ? saved.value : field.value,
        status: saved?.savedAt ? "Reviewed" : "ToBeReviewed",
      };
    }),
    flags: page.flags,
  }));
  return {
    surveyId: survey.id,
    status: pages.every((page) => page.status === "Reviewed")
      ? "Reviewed"
      : "ToBeReviewed",
    pages,
  };
}
