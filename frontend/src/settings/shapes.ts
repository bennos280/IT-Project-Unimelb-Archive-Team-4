import type { Level, Part } from "./PageTypesScreen";

// The common shapes of a record, each filling in what a level is made of: the whole item (no level at all), each page, a run of
// pages from a starting page type, or that with one page type filed elsewhere and matched by number; custom: the parts as set
// by hand.
export type Shape =
  | { kind: "item" }
  | { kind: "page" }
  | { kind: "run"; start: string }
  | { kind: "matched"; start: string; match: string }
  | { kind: "custom" };

// The parts a shape makes of a series' read page types: the starting one (one or more: a second sheet is the same record), every
// other one following it (any number), and the matched one (exactly one, wherever it's filed).
export function partsOf(shape: Shape, read: string[]): Part[] {
  if (shape.kind !== "run" && shape.kind !== "matched") return [];
  const match = shape.kind === "matched" ? shape.match : null;
  return [
    { type: shape.start, count: "one_or_more", how: "starts" },
    ...read.filter((t) => t !== shape.start && t !== match).map((type): Part => ({ type, count: "any", how: "follows" })),
    ...(match ? [{ type: match, count: "one", how: "matched" } as Part] : []),
  ];
}

// The shape a level's parts make, or custom when none makes them.
export function shapeOf(parts: Part[]): Shape {
  if (!parts.length) return { kind: "page" };
  const [first, ...rest] = parts;
  const matched = rest.filter((p) => p.how === "matched");
  if (first.count !== "one_or_more" || rest.some((p) => p.how === "follows" && p.count !== "any") || matched.length > 1 ||
      matched.some((p) => p.count !== "one")) return { kind: "custom" };
  return matched.length ? { kind: "matched", start: first.type, match: matched[0].type } : { kind: "run", start: first.type };
}

// A level in a few words, for the ladder: its shape, or, when custom, how many of each part (by its label) and which are matched.
export function describe(level: Level, label: (type: string) => string) {
  const shape = shapeOf(level.parts);
  const short: Record<Part["count"], string> = { one: "1", one_or_more: "1+", any: "any", at_most_one: "0–1" };
  return shape.kind === "page" ? "One per page"
    : shape.kind === "run" ? `Starts at each ${label(shape.start)}`
    : shape.kind === "matched" ? `Starts at each ${label(shape.start)} · ${label(shape.match)} matched by number`
    : level.parts.map((p) => `${short[p.count]} ${label(p.type)}${p.how === "matched" ? " by number" : ""}`).join(" · ");
}
