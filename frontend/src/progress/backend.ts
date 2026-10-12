export async function backendRequest<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, options);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === "string" ? error.detail : `Request failed (${response.status}).`);
  }
  return response.json();
}
export type AvailableBundle = {
  pdf: string; bundle: string; name: string; loaded: boolean; surveys: string[];
  job: { status: string; step: string | null; donePages: number; totalPages: number; error: string | null } | null;
};
