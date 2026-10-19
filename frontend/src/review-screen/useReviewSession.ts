import { useEffect, useRef, useState } from "react";
import { me } from "../person";
import { getSurvey, getReviews, saveReviews } from "./api";
import type { Survey, Field } from "./model";
import { orderFields } from "./fieldOrder";
type Edit = {
  value: string | null;
  original: string | null;
  reviewer: string;
  reviewerId: number;
  savedAt?: string;
};
type Reviews = Record<string, Record<string, Edit>>;

// Manage the review screen state and expose loading, editing, saving and navigation actions. Reviews are by whoever is working.
export function useReviewSession() {
  const { id: reviewerId, name: reviewer } = me();
  const [reviews, setReviews] = useState<Reviews>({}),
    [editing, setEditing] = useState<Field | null>(null),
    [draft, setDraft] = useState(""),
    [message, setMessage] = useState("");
  const [revisions, setRevisions] = useState<Record<string, number>>({}),
    [saving, setSaving] = useState(false);
  const savedReviews = useRef<Reviews>({});
  const [pendingPage, setPendingPage] = useState<number | null>(null);
  const leaving = pendingPage !== null;
  const [survey, setSurvey] = useState<Survey | null>(null),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0),
    [index, setIndex] = useState(0),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all");
  const surveyId =
    new URLSearchParams(location.search).get("survey")?.trim() ?? "";

  // Reload when the survey or retry counter changes; ignore results after cleanup.
  useEffect(() => {
    if (!surveyId) return;

    const controller = new AbortController();
    Promise.all([
      getSurvey(surveyId, controller.signal),
      getReviews(surveyId),
    ])
      .then(([data, saved]) => {
        if (controller.signal.aborted) return;
        setError("");
        setSurvey(data);
        // Dashboard links select the source page by ID, not by assumed page order.
        const requestedPage = new URLSearchParams(location.search).get("page");
        const requestedIndex = data.pages.findIndex(p => p.id === requestedPage);
        setIndex(requestedIndex < 0 ? 0 : requestedIndex);
        setReviews(saved.reviews);
        savedReviews.current = saved.reviews;
        setRevisions(saved.revisions);
      })
      .catch((e) => {
        if (controller.signal.aborted) return;
        setError(`Could not load this record: ${e.message}`);
      });
    return () => controller.abort();
  }, [surveyId, attempt]);
  const page = survey?.pages[index];
  const pageReviews = page ? reviews[page.id] || {} : {};
  const dirty = Object.values(reviews).some((p) =>
    Object.values(p).some((e) => !e.savedAt),
  );

  // Register the browser leave warning only while applied reviews remain unsaved.
  useEffect(() => {
    if (!dirty) return;

    // Ask the browser to confirm leaving; custom text is controlled by the browser.
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);

  // Open the editor with the latest reviewed value, falling back to the extracted value.
  function beginEdit(field: Field) {
    setEditing(field);
    setDraft(
      (pageReviews[field.id] ? pageReviews[field.id].value : field.value) ?? "",
    );
  }

  // Store the review in memory without a saved timestamp; an empty editor value becomes null.
  function applyEdit() {
    if (!page || !editing) return;
    setReviews((r) => ({
      ...r,
      [page.id]: {
        ...r[page.id],
        [editing.id]: {
          value: draft === "" ? null : draft,
          original: editing.value,
          reviewer,
          reviewerId,
        },
      },
    }));
    setEditing(null);
    setMessage("Field reviewed. Save Page Transcript to save your changes.");
  }

  // Mark every unflagged field with no review yet as pending review; existing reviews keep their value and reviewer.
  function reviewAll() {
    if (!page) return;
    setReviews((r) => ({
      ...r,
      [page.id]: {
        ...r[page.id],
        ...Object.fromEntries(
          page.fields
            .filter(
              (field) =>
                !r[page.id]?.[field.id] &&
                !page.flags.some((flag) => flag.fieldId === field.id),
            )
            .map((field) => [
              field.id,
              {
                value: field.value,
                original: field.value,
                reviewer,
                reviewerId,
              },
            ]),
        ),
      },
    }));
    setMessage(
      "All unflagged fields on this page marked reviewed. Check the flagged fields, then Save Page Transcript to save them to the database.",
    );
  }

  // Save pending fields; update timestamps and the discard snapshot only after a successful response.
  async function savePage() {
    if (!page || saving) return false;
    const pageId = page.id;
    const changed = Object.fromEntries(
      Object.entries(pageReviews)
        .filter(([, e]) => !e.savedAt)
        .map(([id, e]) => [id, { value: e.value, reviewerId: e.reviewerId }]),
    );
    setSaving(true);
    try {
      const result = await saveReviews(
        surveyId,
        pageId,
        revisions[pageId] || 0,
        changed,
      );
      savedReviews.current = {
        ...savedReviews.current,
        [pageId]: Object.fromEntries(
          Object.entries(pageReviews).map(([id, edit]) => [
            id,
            changed[id] ? { ...edit, savedAt: result.savedAt } : edit,
          ]),
        ),
      };
      setRevisions((r) => ({ ...r, [pageId]: result.revision }));
      setReviews((r) => ({
        ...r,
        [pageId]: Object.fromEntries(
          Object.entries(r[pageId]).map(([id, e]) => [
            id,
            changed[id] ? { ...e, savedAt: result.savedAt } : e,
          ]),
        ),
      }));
      setMessage("Page transcript saved.");
      return true;
    } catch (e) {
      setMessage(
        e instanceof Error
          ? e.message
          : "Could not save. Your changes remain unsaved.",
      );
      return false;
    } finally {
      setSaving(false);
    }
  }

  // Switch the displayed page and reset search, flag filters and feedback.
  function changePage(i: number) {
    setIndex(i);
    setQuery("");
    setFilter("all");
    setMessage("");
  }

  // Check page bounds and ask for a save-or-discard decision when reviews are pending.
  function navigate(i: number) {
    if (saving || !survey || i < 0 || i >= survey.pages.length || i === index)
      return;
    if (Object.values(pageReviews).some((review) => !review.savedAt)) {
      setPendingPage(i);
      setMessage("");
      return;
    }
    changePage(i);
  }

  // Close the navigation warning and keep the current page and pending reviews.
  function stayOnPage() {
    if (saving) return;
    setPendingPage(null);
  }

  // Move to the requested page only if saving succeeds; otherwise retain the draft and error.
  async function saveAndContinue() {
    if (pendingPage === null || saving) return;
    const destination = pendingPage;
    if (await savePage()) {
      setPendingPage(null);
      changePage(destination);
    }
  }

  // Restore the current page from its saved snapshot, then continue to the requested page.
  function discardAndContinue() {
    if (pendingPage === null || !page || saving) return;
    setReviews((current) => ({
      ...current,
      [page.id]: savedReviews.current[page.id] || {},
    }));
    changePage(pendingPage);
    setPendingPage(null);
  }

  // Download survey data with the current local review state, including unsaved changes.
  function download() {
    if (!survey) return;
    const url = URL.createObjectURL(
      new Blob(
        [JSON.stringify({ ...survey, localReviews: reviews }, null, 2)],
        { type: "application/json" },
      ),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `survey-${survey.id}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  // Filter by extraction flags and the original field text, label and group.
  const displayFields = page ? orderFields(page.fields, page.type) : [];
  const visible =
    displayFields.filter(
      (f) =>
        (filter === "all" ||
          (!pageReviews[f.id] &&
            page?.flags.some(
              (flag) =>
                flag.fieldId === f.id &&
                (filter === "flagged" || flag.kind === filter),
            ))) &&
        `${f.label} ${f.value ?? ""} ${f.group}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    ) || [];
  const groups = [...new Set(visible.map((f) => f.group))];
  // Flagged fields on this page not yet reviewed, counted like the dashboard's "need checking".
  const flagsLeft = new Set(
    page?.flags
      .filter((flag) => !pageReviews[flag.fieldId])
      .map((flag) => flag.fieldId),
  ).size;
  return {
    survey,
    error,
    attempt,
    setAttempt,
    index,
    query,
    setQuery,
    filter,
    setFilter,
    surveyId,
    page,
    pageReviews,
    flagsLeft,
    reviews,
    reviewer,
    reviewerId,
    editing,
    setEditing,
    draft,
    setDraft,
    message,
    revisions,
    saving,
    beginEdit,
    applyEdit,
    reviewAll,
    savePage,
    navigate,
    leaving,
    stayOnPage,
    saveAndContinue,
    discardAndContinue,
    download,
    visible,
    groups,
  };
}
