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

export function loadExportBundles(collectionId?: number): Promise<Array<{ id: string; name: string }>> {
  return request(collectionId ? `/export/bundles?collection=${collectionId}` : "/export/bundles");
}
export function loadBundleExport(bundleId: string): Promise<SurveyExport> {
  const id = bundleId.trim();
  if (!id) throw new Error("Choose an item.");
  return request(`/export?bundle_id=${encodeURIComponent(id)}`);
}
