// What a series has that setting it up asks for: page types of its own, how many have a template, its pages (all, and those
// waiting as Unknown), its items read, its readings running, and its levels of record.
export type SeriesCounts = {
  pageTypes: number; templates: number; pages: number; unknownPages: number; bundles: number; running: number; levels?: unknown[];
};

// Which steps of setting a series up are done: it has page types, each has a template, some pages were read as one of them (an
// item read as a sample), and, optionally, it says what a record is.
export const setUpSteps = (c: SeriesCounts) => ({
  types: c.pageTypes > 0,
  templates: c.pageTypes > 0 && c.templates >= c.pageTypes,
  sample: c.pages - c.unknownPages > 0,
  record: (c.levels ?? []).length > 0,
});

// A series is set up, and its items can be read, once the steps that aren't optional are done.
export const isSetUp = (c: SeriesCounts) => {
  const done = setUpSteps(c);
  return done.types && done.templates && done.sample;
};
