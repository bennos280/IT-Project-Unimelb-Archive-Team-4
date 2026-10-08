// Fetch the backend-generated export; never combine it with browser drafts.
import { request } from "../review-screen/api";
import type { SurveyExport } from "./exportData";

export async function loadSurveyExport(
  surveyId: string,
): Promise<SurveyExport> {
  const id = surveyId.trim();
  if (!id) throw new Error("Enter a survey ID.");
  return request<SurveyExport>(`/export?survey_id=${encodeURIComponent(id)}`);
}
