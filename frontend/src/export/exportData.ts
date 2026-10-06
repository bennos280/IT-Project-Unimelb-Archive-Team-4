// Builds export records using saved corrections while preserving source references and review statuses.
// TODO: Update the survey JSON structure to match the agreed Archives layout.
// TODO: Add bundle JSON export using the agreed structure and US8 bundle data.
import type { Survey } from "../review-screen/model";

// Represents a previously saved review value for a survey field.

type SavedReview = {
  value: string | null;
  savedAt?: string;
};

// Stores saved reviews by page ID and field ID.
export type SavedReviews = Record<string, Record<string, SavedReview>>;

/**
 * Exports every field on every page of a survey.
 * Uses a saved correction when available; otherwise keeps the extracted value.
 * Unsaved draft changes from the current review session are ignored.
 */
export function buildSurveyExport(survey: Survey, reviews: SavedReviews) {
  // Convert each survey page into its export representation.
  const pages = survey.pages.map((page) => ({
    pageId: page.id,
    label: page.type,

    // Preserve the original source image reference.
    sourceImage: page.imageUrl,

    // A page is reviewed only when every field has a saved review.
    status:
      page.fields.every((field) => reviews[page.id]?.[field.id]?.savedAt) &&
      page.fields.length > 0
        ? "Reviewed"
        : "ToBeReviewed",

    // Export all fields using their latest persisted value when available.
    fields: page.fields.map((field) => {
      const saved = reviews[page.id]?.[field.id];

      // Validate saved values before adding them to the export.
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

        // Prefer a saved correction, otherwise use the original extracted value.
        value: saved?.savedAt ? saved.value : field.value,

        // Mark individual fields according to whether they have been saved.
        status: saved?.savedAt ? "Reviewed" : "ToBeReviewed",
      };
    }),

    // Preserve any validation flags attached to the page.
    flags: page.flags,
  }));

  // Build the final survey-level export record.
  return {
    surveyId: survey.id,

    // The whole survey is reviewed only when every page is reviewed.
    status: pages.every((page) => page.status === "Reviewed")
      ? "Reviewed"
      : "ToBeReviewed",

    pages,
  };
}
