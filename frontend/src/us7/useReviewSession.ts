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
type Edit = {
  value: string | null;
  original: string | null;
  reviewer: string;
  reviewerId: number;
  savedAt?: string;
};
type Reviews = Record<string, Record<string, Edit>>;
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
  const [survey, setSurvey] = useState<Survey | null>(null),
    [error, setError] = useState(""),
    [attempt, setAttempt] = useState(0),
    [index, setIndex] = useState(0),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState("all");
  const surveyId =
    new URLSearchParams(location.search).get("survey") || "216417";
  useEffect(() => {
    const controller = new AbortController();
    setError("");
    Promise.all([
      getSurvey(surveyId, controller.signal),
      getReviews(surveyId),
      getReviewers(),
    ])
      .then(([data, saved, people]) => {
        setSurvey(data);
        setReviews(saved.reviews);
        setRevisions(saved.revisions);
        setReviewers(people);
      })
      .catch((e) => {
        if (e.name !== "AbortError")
          setError(`Could not load sample data: ${e.message}`);
      });
    return () => controller.abort();
  }, [surveyId, attempt]);
  const page = survey?.pages[index];
  const pageReviews = page ? reviews[page.id] || {} : {};
  const dirty = Object.values(reviews).some((p) =>
    Object.values(p).some((e) => !e.savedAt),
  );
  useEffect(() => {
    if (!dirty) return;
    const warn = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty]);
  function beginEdit(field: Field) {
    setEditing(field);
    setDraft(
      (pageReviews[field.id] ? pageReviews[field.id].value : field.value) ?? "",
    );
    editor.current?.showModal();
  }
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
    setMessage(
      "Field reviewed. Save Page Transcript to save your changes in this browser.",
    );
  }
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
  function reviewAll() {
    if (!page || !reviewer) return;
    setReviews((r) => ({
      ...r,
      [page.id]: Object.fromEntries(
        page.fields.map((field) => [
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
    }));
    setMessage(
      "All fields on this page marked reviewed. Save Page Transcript to save this in this browser. Flags remain visible.",
    );
  }
  async function savePage() {
    if (!page || !reviewer || saving) return;
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
      setMessage("Page transcript saved in this browser.");
    } catch (e) {
      setMessage(
        e instanceof Error
          ? e.message
          : "Could not save. Your changes remain unsaved.",
      );
    } finally {
      setSaving(false);
    }
  }
  function navigate(i: number) {
    setIndex(i);
    setQuery("");
    setFilter("all");
    setMessage("");
  }
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
  const visible =
    page?.fields.filter(
      (f) =>
        (filter === "all" ||
          page.flags.some((flag) => flag.fieldId === f.id)) &&
        `${f.label} ${f.value ?? ""} ${f.group}`
          .toLowerCase()
          .includes(query.toLowerCase()),
    ) || [];
  const groups = [...new Set(visible.map((f) => f.group))];
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
    download,
    visible,
    groups,
  };
}
