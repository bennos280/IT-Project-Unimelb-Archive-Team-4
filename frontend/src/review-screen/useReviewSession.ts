import { useEffect, useRef, useState } from "react";
import {
  getSurvey,
  getReviewers,
  createReviewer,
  getReviews,
  saveReviews,
  type Reviewer,
} from "./api";
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

// Manage the review screen state and expose loading, editing, saving and navigation actions.
export function useReviewSession() {
  const [reviews, setReviews] = useState<Reviews>({}),
    [reviewer, setReviewer] = useState(""),
    [reviewers, setReviewers] = useState<Reviewer[]>([]),
    [newName, setNewName] = useState(""),
    [adding, setAdding] = useState(false),
    [editing, setEditing] = useState<Field | null>(null),
    [draft, setDraft] = useState(""),
    [message, setMessage] = useState("");
  const [revisions, setRevisions] = useState<Record<string, number>>({}),
    [saving, setSaving] = useState(false);
  const editor = useRef<HTMLDialogElement>(null);
  const navigationDialog = useRef<HTMLDialogElement>(null);
  const savedReviews = useRef<Reviews>({});
  const [pendingPage, setPendingPage] = useState<number | null>(null);
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
      getReviewers(),
    ])
      .then(([data, saved, people]) => {
        if (controller.signal.aborted) return;
        setError("");
        setSurvey(data);
        setReviews(saved.reviews);
        savedReviews.current = saved.reviews;
        setRevisions(saved.revisions);
        setReviewers(people);
      })
      .catch((e) => {
        if (controller.signal.aborted) return;
        setError(`Could not load survey: ${e.message}`);
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
    editor.current?.showModal();
  }

  // Store the review in memory without a saved timestamp; an empty editor value becomes null.
  function applyEdit() {
    if (!page || !editing || !reviewer.trim()) return;
    setReviews((r) => ({
      ...r,
      [page.id]: {
        ...r[page.id],
        [editing.id]: {
          value: draft === "" ? null : draft,
          original: editing.value,
          reviewer,
          reviewerId: reviewers.find((r) => r.name === reviewer)!.id,
        },
      },
    }));
    editor.current?.close();
    setEditing(null);
    setMessage("Field reviewed. Save Page Transcript to save your changes.");
  }

  // Create or retrieve a reviewer, update the selector and show any backend error.
  async function addReviewer() {
    const name = newName.trim();
    if (!name) return;
    try {
      const person = await createReviewer(name);
      setReviewers((r) => [...r.filter((p) => p.id !== person.id), person]);
      setReviewer(person.name);
      setAdding(false);
      setNewName("");
      setMessage("Reviewer added in this browser.");
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Could not add reviewer.");
    }
  }

  // Mark every unflagged field on the current page as pending review without replacing existing corrections.
  function reviewAll() {
    if (!page || !reviewer) return;
    setReviews((r) => ({
      ...r,
      [page.id]: {
        ...r[page.id],
        ...Object.fromEntries(
          page.fields
            .filter(
              (field) => !page.flags.some((flag) => flag.fieldId === field.id),
            )
            .map((field) => [
              field.id,
              {
                value: r[page.id]?.[field.id]
                  ? r[page.id][field.id].value
                  : field.value,
                original: field.value,
                reviewer,
                reviewerId: reviewers.find((r) => r.name === reviewer)!.id,
              },
            ]),
        ),
      },
    }));
    setMessage(
      "All unflagged fields on this page marked reviewed. Check flagged fields one by one, then Save Page Transcript.",
    );
  }

  // Save pending fields; update timestamps and the discard snapshot only after a successful response.
  async function savePage() {
    if (!page || !reviewer || saving) return false;
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
      navigationDialog.current?.showModal();
      return;
    }
    changePage(i);
  }

  // Close the navigation warning and keep the current page and pending reviews.
  function stayOnPage() {
    if (saving) return;
    navigationDialog.current?.close();
    setPendingPage(null);
  }

  // Move to the requested page only if saving succeeds; otherwise retain the draft and error.
  async function saveAndContinue() {
    if (pendingPage === null || saving) return;
    const destination = pendingPage;
    if (await savePage()) {
      navigationDialog.current?.close();
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
    navigationDialog.current?.close();
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
    setReviewer,
    reviewers,
    newName,
    setNewName,
    adding,
    setAdding,
    editing,
    setEditing,
    draft,
    setDraft,
    message,
    revisions,
    saving,
    editor,
    beginEdit,
    applyEdit,
    addReviewer,
    reviewAll,
    savePage,
    navigate,
    navigationDialog,
    stayOnPage,
    saveAndContinue,
    discardAndContinue,
    download,
    visible,
    groups,
  };
}
