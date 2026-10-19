// Sends requests through the frontend /api route. T describes the expected JSON
// response for TypeScript; it does not validate the response at runtime.
export async function backendRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    // Prefer FastAPI’s detail message (or list of messages, one a line); fall back to the HTTP status for non-JSON errors.
    const error = await response.json().catch(() => ({}));
    const list = Array.isArray(error.detail) && error.detail.every((d: unknown) => typeof d === "string");
    throw new Error(typeof error.detail === "string" ? error.detail : list ? error.detail.join("\n") : `Request failed (${response.status}).`);
  }
  // 204 No Content (e.g. a DELETE) has no body to parse.
  if (response.status === 204) return undefined as T;
  return response.json();
}
export const providerNames: Record<string, string> = { claude: "Claude Code", codex: "Codex CLI" };
// The archive's website; a series' page is /nodes/view/<its number>, and an item's /nodes/view/<its name>.
export const ARCHIVE = "https://archives.library.unimelb.edu.au";
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
export type ArchiveItem = { identifier: string; title: string };
// What a series calls one record, several, and one with its article, mid-sentence and starting one.
// ponytail: English's usual plurals and "an" before a vowel letter; irregular ones (person, hour) come out wrong.
export function recordWords(one = "record") {
  const many = /[^aeiou]y$/.test(one) ? `${one.slice(0, -1)}ies` : /(s|x|ch|sh)$/.test(one) ? `${one}es` : `${one}s`;
  const a = `${/^[aeiou]/.test(one) ? "an" : "a"} ${one}`;
  const start = (word: string) => word.charAt(0).toUpperCase() + word.slice(1);
  return { one, many, a, One: start(one), A: start(a) };
}
// An item's name on screen: its title on the archive, else its number.
export const itemTitle = (name: string, archive?: ArchiveItem | null) => archive?.title ?? `Item ${name}`;
// An item as the series' items list gives it, with its current processing job.
// loaded means it has been imported into the database; job can be absent; archive is null when it isn't one of the series' archive items.
export type AvailableBundle = {
  pdf: string; bundle: string; name: string; archive: ArchiveItem | null; loaded: boolean;
  job: { id?: number; status: string; step: string | null; donePages: number; totalPages: number; error: string | null } | null;
};
