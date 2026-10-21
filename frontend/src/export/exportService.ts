// Fetch the backend-generated export; never combine it with browser drafts.
import { request } from "../review-screen/api";
import type { SurveyExport } from "./exportData";

export async function loadSurveyExport(
  surveyId: string,
): Promise<SurveyExport> {
  const id = surveyId.trim();
  if (!id) throw new Error("Enter a record ID.");
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

// The series' zip, under the file name the server gives it.
export async function loadSeriesExport(collectionId: number): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(`/api/collections/${collectionId}/export`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(typeof body.detail === "string" ? body.detail : `Request failed (${response.status}).`);
  }
  const filename = response.headers.get("Content-Disposition")?.match(/filename="?([^";]+)"?/)?.[1] ?? "series-export.zip";
  return { blob: await response.blob(), filename };
}
