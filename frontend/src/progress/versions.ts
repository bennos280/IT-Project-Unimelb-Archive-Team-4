// GET /instruction-versions: every prompt and template version, oldest first; number counts the versions of one kind from 1
export type Version = { id: number; kind: string; label: string; number: number; current: boolean; body: string;
  reviewer: string | null; note: string | null; createdAt: string };

// What a kind of version is called: the prompt, or a page type's template.
export const versionName = (v: Pick<Version, "kind" | "label">) => (v.kind === "prompt" ? "Prompt" : `${v.label} template`);

type Line = { kind: "same" | "add" | "del"; text: string };
// gap: a run of unchanged lines left out
export type DiffRow = Line | { kind: "gap"; count: number };

// A run of unchanged lines longer than this is folded to CONTEXT lines beside each change; a run at an end has them on its one side.
const FOLD_OVER = 6;
const CONTEXT = 3;

// Line endings are made LF first; an empty text has no lines, and a newline at the end ends the last line.
function toLines(text: string) {
  const lf = text.replace(/\r\n?/g, "\n");
  return lf === "" ? [] : lf.replace(/\n$/, "").split("\n");
}

// The removed lines of a change come before the lines added.
function diffLines(before: string, after: string): Line[] {
  const [a, b] = [before, after].map(toLines);
  // ponytail: O(n·m) table of line pairs
  const lcs = Array.from({ length: a.length + 1 }, () => new Array<number>(b.length + 1).fill(0));
  for (let i = a.length - 1; i >= 0; i--)
    for (let j = b.length - 1; j >= 0; j--) lcs[i][j] = a[i] === b[j] ? lcs[i + 1][j + 1] + 1 : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const out: Line[] = [];
  let i = 0, j = 0;
  while (i < a.length || j < b.length) {
    if (i < a.length && j < b.length && a[i] === b[j]) { out.push({ kind: "same", text: a[i] }); i++; j++; }
    else if (i < a.length && (j === b.length || lcs[i + 1][j] >= lcs[i][j + 1])) out.push({ kind: "del", text: a[i++] });
    else out.push({ kind: "add", text: b[j++] });
  }
  return out;
}

// How one text differs from the one before it, line by line, with the long runs of unchanged lines folded.
export function diffRows(before: string, after: string): DiffRow[] {
  const lines = diffLines(before, after);
  const rows: DiffRow[] = [];
  for (let start = 0; start < lines.length;) {
    let end = start + 1;
    if (lines[start].kind === "same") {
      while (end < lines.length && lines[end].kind === "same") end++;
      const run = lines.slice(start, end);
      if (run.length <= FOLD_OVER) rows.push(...run);
      else {
        const [head, tail] = [start === 0 ? 0 : CONTEXT, end === lines.length ? 0 : CONTEXT];
        rows.push(...run.slice(0, head), { kind: "gap", count: run.length - head - tail }, ...run.slice(run.length - tail));
      }
    } else rows.push(lines[start]);
    start = end;
  }
  return rows;
}
