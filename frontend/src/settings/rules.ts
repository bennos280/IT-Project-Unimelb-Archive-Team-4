// What a template's field should hold (backend/db/checks.py); a value that breaks it is flagged for review.
export type RuleType = "text" | "number" | "date" | "yes_no" | "one_of" | "several_of" | "pattern";
export type Rule = {
  type: RuleType; required?: boolean; min?: string; max?: string; values?: string[]; pattern?: string; example?: string;
};
export type Rules = Record<string, Rule>;
export type Template = { [key: string]: Template | string | null | unknown[] };

export const ruleTypes: Record<RuleType, string> = {
  text: "Text", number: "Number", date: "Date", yes_no: "Yes or no", one_of: "One of a list", several_of: "Several of a list",
  pattern: "Pattern",
};

// A template's fields rules can be set on: each one's dotted path and description (null: none). Lists (residents) aren't checked.
export function fieldsOf(template: Template, parent = ""): [string, string | null][] {
  return Object.entries(template).flatMap(([key, value]): [string, string | null][] => {
    const path = parent ? `${parent}.${key}` : key;
    if (Array.isArray(value)) return [];
    return value !== null && typeof value === "object" ? fieldsOf(value as Template, path) : [[path, typeof value === "string" ? value : null]];
  });
}

export function parseTemplate(text: string | null): Template | null {
  try {
    const parsed: unknown = JSON.parse(text ?? "");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed as Template : null;
  } catch {
    return null;
  }
}

// The rules as saved: only fields still in the template, only what each rule's type uses, nothing left at its default.
export function cleanRules(rules: Rules, template: Template | null): Rules {
  const fields = new Set(template ? fieldsOf(template).map(([path]) => path) : []);
  const clean: Rules = {};
  for (const [path, rule] of Object.entries(rules)) {
    if (!fields.has(path)) continue;
    const kept: Rule = { type: rule.type };
    if (rule.required) kept.required = true;
    if (rule.type === "number" || rule.type === "date") {
      if (rule.min?.trim()) kept.min = rule.min.trim();
      if (rule.max?.trim()) kept.max = rule.max.trim();
    }
    if (rule.type === "one_of" || rule.type === "several_of") kept.values = (rule.values ?? []).map((v) => v.trim()).filter(Boolean);
    if (rule.type === "pattern") {
      kept.pattern = rule.pattern ?? "";
      if (rule.example?.trim()) kept.example = rule.example.trim();
    }
    if (Object.keys(kept).length > 1 || kept.type !== "text") clean[path] = kept;
  }
  return clean;
}

// The template with one field's description set (blank: none, null), as the template's textarea shows it.
export function describe(template: Template, path: string, description: string) {
  const copy = structuredClone(template);
  const keys = path.split(".");
  let at = copy;
  for (const key of keys.slice(0, -1)) at = at[key] as Template;
  at[keys[keys.length - 1]] = description.trim() ? description : null;
  return JSON.stringify(copy, null, 2);
}
