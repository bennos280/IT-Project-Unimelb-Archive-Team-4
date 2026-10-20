// The common shapes of a record and the parts each makes.
import { expect, it } from "vitest";
import { describe as summary, partsOf, shapeOf } from "../../../frontend/src/settings/shapes";

const read = ["coded", "main", "notes"];
const label = (type: string) => ({ coded: "Coded page", main: "Main page", notes: "Notes page" })[type] ?? type;

it("makes a shape's parts: the starting page type, every other one following it, and the matched one", () => {
  expect(partsOf({ kind: "page" }, read)).toEqual([]);
  expect(partsOf({ kind: "run", start: "notes" }, read)).toEqual([{ type: "notes", count: "one_or_more", how: "starts" },
    { type: "coded", count: "any", how: "follows" }, { type: "main", count: "any", how: "follows" }]);
  expect(partsOf({ kind: "matched", start: "main", match: "coded" }, read)).toEqual([{ type: "main", count: "one_or_more", how: "starts" },
    { type: "notes", count: "any", how: "follows" }, { type: "coded", count: "one", how: "matched" }]); // the Prest survey
});

it("finds the shape a level's parts make, or custom when none makes them, and says it in a few words", () => {
  const prest = partsOf({ kind: "matched", start: "main", match: "coded" }, read);
  expect(shapeOf(prest)).toEqual({ kind: "matched", start: "main", match: "coded" });
  expect(shapeOf(prest.slice(0, 2))).toEqual({ kind: "run", start: "main" }); // a type left out still runs from its start
  expect(shapeOf([])).toEqual({ kind: "page" });
  for (const parts of [
    [{ ...prest[0], count: "one" as const }, ...prest.slice(1)], // one of the starting page only
    [prest[0], { ...prest[1], count: "at_most_one" as const }, prest[2]], // a notes page at most
    [prest[0], { ...prest[1], how: "matched" as const, count: "one" as const }, prest[2]]]) // two matched
    expect(shapeOf(parts)).toEqual({ kind: "custom" });
  expect([summary({ name: "survey", key: "n", parts: prest }, label), summary({ name: "card", key: null, parts: [] }, label),
    summary({ name: "letter", key: null, parts: prest.slice(0, 2) }, label)]).toEqual([
    "Starts at each Main page · Coded page matched by number", "One per page", "Starts at each Main page"]);
  expect(summary({ name: "survey", key: "n", parts: [{ ...prest[0], count: "one" }, prest[2]] }, label)).toBe("1 Main page · 1 Coded page by number");
});
