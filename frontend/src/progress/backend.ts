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
// Bundle metadata returned by /bundles, including its current processing job.
// loaded means it has been imported into the database; job can be absent.
export type AvailableBundle = {
  pdf: string; bundle: string; name: string; loaded: boolean; surveys: string[];
  job: { id?: number; status: string; step: string | null; donePages: number; totalPages: number; error: string | null } | null;
};
