// Sends requests through the frontend /api route. T describes the expected JSON
// response for TypeScript; it does not validate the response at runtime.
export async function backendRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    // Prefer FastAPI’s detail message; fall back to the HTTP status for non-JSON errors.
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `Request failed (${response.status}).`);
  }
  // 204 No Content (e.g. a DELETE) has no body to parse.
  if (response.status === 204) return undefined as T;
  return response.json();
}
export const providerNames: Record<string, string> = { claude: "Claude Code", codex: "Codex CLI" };
// The series and the item a page's address names (/?series=<id>&item=<name>), or an older link's ?collection= and ?bundle=.
export const seriesParam = (params: URLSearchParams) => params.get("series") ?? params.get("collection");
export const itemParam = (params: URLSearchParams) => params.get("item") ?? params.get("bundle");
// What a bundle's processing step is doing, in words for reviewers.
export const jobStages: Record<string, string> = {
  split: "Preparing page images (downloads PDF if needed)",
  identify: "Identifying page types",
  preprocess: "Preparing images",
  transcribe: "Transcribing pages",
  group: "Grouping pages",
  validate: "Checking the transcriptions' fields",
  load: "Saving results to database",
};
// What a series calls one record, several, and one with its article, mid-sentence and starting one.
// ponytail: English's usual plurals and "an" before a vowel letter; irregular ones (person, hour) come out wrong.
export function recordWords(one = "record") {
  const many = /[^aeiou]y$/.test(one) ? `${one.slice(0, -1)}ies` : /(s|x|ch|sh)$/.test(one) ? `${one}es` : `${one}s`;
  const a = `${/^[aeiou]/.test(one) ? "an" : "a"} ${one}`;
  const start = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);
  return { one, many, a, One: start(one), A: start(a) };
}
// An item's name on screen: its number.
export const itemTitle = (name: string) => `Item ${name}`;
// An item as the series' items list gives it, with its current processing job.
// loaded means it has been imported into the database; job can be absent.
export type AvailableBundle = {
  pdf: string; bundle: string; name: string; loaded: boolean;
  job: { id?: number; status: string; step: string | null; donePages: number; totalPages: number; error: string | null } | null;
};
