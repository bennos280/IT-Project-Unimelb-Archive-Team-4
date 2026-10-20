// The words a series' record name gives the screens.
import { expect, it } from "vitest";
import { recordWords } from "../../../frontend/src/progress/backend";

it("gives a record name's plural, its article and the forms that start a sentence", () => {
  expect(recordWords("survey")).toEqual({ one: "survey", many: "surveys", a: "a survey", One: "Survey", A: "A survey" });
  expect([recordWords("diary entry").many, recordWords("census").many, recordWords("box").many, recordWords("day").many])
    .toEqual(["diary entries", "censuses", "boxes", "days"]);
  expect([recordWords("envelope").a, recordWords("item").A]).toEqual(["an envelope", "An item"]);
  expect(recordWords().one).toBe("record");
});
