export type Template = { [key: string]: Template | string | null | unknown[] };

export function parseTemplate(text: string | null): Template | null {
  try {
    const parsed: unknown = JSON.parse(text ?? "");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Template : null;
  } catch {
    return null;
  }
}
