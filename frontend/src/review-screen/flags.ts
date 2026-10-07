import type { Flag } from "./model";

// Categories offered by US7 while the detailed US8 validation contract is agreed.
export const flagCategories = {
  between_page_mismatch: "Between-page mismatch",
  total_mismatch: "Total mismatch",
  count_exceeds_total: "Count exceeds total",
  uncertain: "Uncertain values",
};

export const flagLabels: Record<Flag["kind"], string> = {
  ...flagCategories,
  inconsistency: "Internal inconsistency",
  gibberish: "Possible gibberish",
};

