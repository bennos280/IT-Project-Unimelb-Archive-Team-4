// Exports every page and field using the latest values saved in US8.
// TODO: Update the survey JSON structure to match the agreed Archives layout.
// TODO: Add bundle JSON export using the agreed structure and US8 bundle data.
import { getReviews, getSurvey } from "../review-screen/api";
import { buildSurveyExport } from "./exportData";

export async function loadSurveyExport(surveyId: string) {
  const id = surveyId.trim();

  if (!id) {
    throw new Error("Enter a survey ID.");
  }

  const [survey, saved] = await Promise.all([getSurvey(id), getReviews(id)]);

  const record = buildSurveyExport(survey, saved.reviews);

  return {
    surveys: [record],
  };
}
