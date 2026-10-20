// Whether a series is set up, from what it has.
import { expect, it } from "vitest";
import { isSetUp, setUpSteps } from "../../../frontend/src/progress/setup";

const prest = { pageTypes: 3, templates: 3, pages: 8853, unknownPages: 463, bundles: 26, running: 0, levels: [{}] };

it("is set up with page types of its own, a template for each, and pages read as one of them; a level is optional", () => {
  expect([isSetUp(prest), isSetUp({ ...prest, levels: [] })]).toEqual([true, true]);
  expect(isSetUp({ ...prest, pageTypes: 0, templates: 0 })).toBe(false); // only its Unknown type
  expect(isSetUp({ ...prest, templates: 2 })).toBe(false); // a page type with no template
  expect(isSetUp({ ...prest, pages: 463 })).toBe(false); // read, but every page waits as Unknown
  expect(setUpSteps({ ...prest, templates: 2, pages: 0, unknownPages: 0, levels: [] })).toEqual(
    { types: true, templates: false, sample: false, record: false });
});
