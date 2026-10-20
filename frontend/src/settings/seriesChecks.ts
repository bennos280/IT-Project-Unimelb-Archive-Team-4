// A series' checks across fields (backend/db/checks.py). A check names fields as "<page type>.<field path>": it compares them (several
// on a side are added up; as codes, only values all digits) with fields or a value, or says one field is the name another's code has in
// its list, or that if one is so another must be. A value failing it is flagged for review.
export type Op = "=" | "!=" | "<" | "<=" | ">" | ">=" | "names";
export type State = "filled" | "empty" | "is";
export type Check = {
  id: string; kind: "compare" | "if"; on?: boolean; message?: string;
  left?: string[]; op?: Op; right?: string[]; value?: string; as?: "codes";
  if?: string; is?: State; isValue?: string; then?: string; must?: State; mustValue?: string;
};
export type CheckVersion = { id: number; number: number; checks: Check[]; reviewer: string | null; note: string | null; createdAt: string };
// Each of the series' page types with the fields of its newest template, to choose from.
export type FieldChoice = { type: string; label: string; fields: string[] };

export const ops: Record<Op, string> = { "=": "=", "!=": "≠", "<": "<", "<=": "≤", ">": ">", ">=": "≥", names: "names" };
export const states: Record<State, [string, string]> = { filled: ["is filled", "be filled"], empty: ["is empty", "be empty"], is: ["is", "be"] };

export const newCheck = (): Check => ({ id: crypto.randomUUID().slice(0, 8), kind: "compare", left: [""], op: "=", right: [""] });

// A check as saved: only what its kind uses, its fields chosen, on unless switched off.
export function cleanCheck(check: Check): Check {
  const base: Check = { id: check.id, kind: check.kind, ...(check.on === false ? { on: false } : {}),
    ...(check.message?.trim() ? { message: check.message.trim() } : {}) };
  if (check.kind === "if") {
    return { ...base, if: check.if, is: check.is, ...(check.is === "is" ? { isValue: check.isValue?.trim() } : {}), then: check.then,
      must: check.must, ...(check.must === "is" ? { mustValue: check.mustValue?.trim() } : {}) };
  }
  return { ...base, left: (check.left ?? []).filter(Boolean), op: check.op,
    ...(check.value !== undefined && check.op !== "names" ? { value: check.value.trim() } : { right: (check.right ?? []).filter(Boolean) }),
    ...(check.as === "codes" && check.op !== "names" ? { as: "codes" as const } : {}) };
}

// Why a check can't be added yet; "" if it can. A field no longer in its page type's template must be chosen again.
export function unfinished(check: Check, choices: FieldChoice[]) {
  const known = new Set(choices.flatMap((c) => c.fields.map((f) => `${c.type}.${f}`)));
  const named = check.kind === "if" ? [check.if, check.then] : [...(check.left ?? []), ...(check.value === undefined ? check.right ?? [] : [])];
  if (named.some((ref) => ref && !known.has(ref))) return "A field it names is no longer in its page type's template: choose it again.";
  if (check.kind === "if") {
    if (!check.if || !check.then) return "Choose both fields.";
    if ((check.is === "is" && !check.isValue?.trim()) || (check.must === "is" && !check.mustValue?.trim())) return "Give the value.";
    return "";
  }
  if (!check.left?.length || check.left.some((f) => !f)) return "Choose the fields to compare.";
  if (check.op === "names" && (check.left.length !== 1 || check.value !== undefined || check.right?.length !== 1)) {
    return "Names compares one field with one coded field.";
  }
  if (check.value !== undefined ? !check.value.trim() : !check.right?.length || check.right.some((f) => !f)) return "Choose what to compare them with.";
  return "";
}

// A check in words, with each field as "<page type label> › <field>": "Main page › rooms.living + … = Coded page › total_rooms".
export function sentence(check: Check, choices: FieldChoice[]) {
  const name = (ref = "") => {
    const [type, ...path] = ref.split(".");
    return `${choices.find((c) => c.type === type)?.label ?? type} › ${path.join(".")}`;
  };
  if (check.kind === "if") {
    return `If ${name(check.if)} ${states[check.is ?? "filled"][0]}${check.is === "is" ? ` ${check.isValue}` : ""}, then ${name(check.then)}`
      + ` must ${states[check.must ?? "filled"][1]}${check.must === "is" ? ` ${check.mustValue}` : ""}`;
  }
  const side = (fields: string[] = []) => fields.map(name).join(" + ");
  return `${side(check.left)} ${ops[check.op ?? "="]} ${check.value !== undefined ? check.value : side(check.right)}${check.as === "codes" ? " (as codes)" : ""}`;
}
