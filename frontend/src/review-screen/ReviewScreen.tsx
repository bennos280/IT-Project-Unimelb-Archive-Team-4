// Main review screen: field table on the left, scan viewer on the right.

import React, { useState } from "react";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Search,
  TriangleAlert,
  Download,
  Pencil,
} from "lucide-react";
import ImageViewer from "./ImageViewer";
import type { useReviewSession } from "./useReviewSession";
import { pageNames as names } from "./model";
import "./review.css";
import { flagCategories, flagLabels } from "./flags";

// Render extracted fields and the scan, wiring reviewer controls and dialogs to session actions.
export default function ReviewScreen({
  session,
}: {
  session: ReturnType<typeof useReviewSession>;
}) {
  const [collapsedGroups, setCollapsedGroups] = useState<
    Record<string, boolean>
  >({});
  const [statusFilter, setStatusFilter] = useState("all");
  const [selection, setSelection] = useState<{
    pageId: string;
    fieldId: string;
    token: number;
  } | null>(null);
  const {
    survey,
    error,
    setAttempt,
    index,
    query,
    setQuery,
    filter,
    setFilter,
    page,
    pageReviews,
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
    visible: matchingFields,
  } = session;
  // Filter by the same saved/draft status shown in each row.
  const visible = matchingFields.filter((field) => {
    const review = pageReviews[field.id];
    const status = review
      ? review.savedAt
        ? "Reviewed"
        : "Unsaved"
      : field.value === null || field.value === ""
        ? "Blank"
        : "Transcribed";
    return statusFilter === "all" || statusFilter === status;
  });
  const groups = [...new Set(visible.map((field) => field.group))];
  return (
    <>
      <header className="topbar">
        <div>
          <h1>Wilfred Prest Survey</h1>
          <p>Review Survey Card</p>
        </div>
      </header>
      <main>
        {!session.surveyId ? (
          <div className="empty" role="status">
            Select a survey to review.
          </div>
        ) : error ? (
          <div className="empty" role="alert">
            {error}
            <button onClick={() => setAttempt((a) => a + 1)}>Try again</button>
          </div>
        ) : !page || !survey ? (
          <div className="empty" role="status">
            Loading survey and source images…
          </div>
        ) : (
          <div className="review-grid">
            <section className="extracted">
              <div className="page-heading">
                <h2>
                  {page.id} · {names[page.type]}
                </h2>
                <span className="review-progress">
                  {page.fields.length
                    ? Math.round(
                        (Object.keys(pageReviews).length / page.fields.length) *
                          100,
                      )
                    : 0}
                  % reviewed
                </span>
                {/* TODO:support page-category changes
                <button disabled title="Change page category not implemented yet">
                  Change page category
                </button>
                */}
              </div>
              <div className="filters">
                <label className="search">
                  <Search size={15} />
                  <input
                    aria-label="Search fields"
                    placeholder="Search fields…"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                  />
                </label>
              </div>
              <div className="field-scroll" key={page.id}>
                {!visible.length ? (
                  <div className="empty">
                    No fields match your filters.
                    <button
                      onClick={() => {
                        setQuery("");
                        setFilter("all");
                        setStatusFilter("all");
                      }}
                    >
                      Clear filters
                    </button>
                  </div>
                ) : (
                  <table
                    className={
                      page.type === "notes" ? "notes-table" : undefined
                    }
                  >
                    <thead>
                      <tr>
                        <th>Sub-field</th>
                        <th>Value</th>
                        <th>
                          <select
                            className="flag-filter"
                            aria-label="Filter fields"
                            value={filter}
                            onChange={(e) => setFilter(e.target.value)}
                          >
                            <option value="all">Flag</option>
                            <option value="flagged">All flagged fields</option>
                            {Object.entries(flagCategories).map(([value, label]) => (
                              <option key={value} value={value}>{label}</option>
                            ))}
                          </select>
                        </th>
                        <th>
                          <select
                            className="status-filter"
                            aria-label="Filter by review status"
                            value={statusFilter}
                            onChange={(event) =>
                              setStatusFilter(event.target.value)
                            }
                          >
                            <option value="all">Status</option>
                            {[
                              "Reviewed",
                              "Unsaved",
                              "Blank",
                              "Transcribed",
                            ].map((status) => (
                              <option key={status} value={status}>
                                {status}
                              </option>
                            ))}
                          </select>
                        </th>
                      </tr>
                    </thead>
                    {groups.map((group) => (
                      <tbody key={group}>
                        <tr className="group-row">
                          <th colSpan={4}>
                            <button
                              className="group-toggle"
                              aria-expanded={
                                !collapsedGroups[
                                  JSON.stringify([survey.id, page.id, group])
                                ]
                              }
                              onClick={() => {
                                const key = JSON.stringify([
                                  survey.id,
                                  page.id,
                                  group,
                                ]);
                                setCollapsedGroups((current) => ({
                                  ...current,
                                  [key]: !current[key],
                                }));
                              }}
                            >
                              {collapsedGroups[
                                JSON.stringify([survey.id, page.id, group])
                              ] ? (
                                <ChevronRight size={16} aria-hidden="true" />
                              ) : (
                                <ChevronDown size={16} aria-hidden="true" />
                              )}
                              {group}
                            </button>
                          </th>
                        </tr>
                        {!collapsedGroups[
                          JSON.stringify([survey.id, page.id, group])
                        ] &&
                          visible
                            .filter((f) => f.group === group)
                            .map((field) => {
                              const flags = page.flags.filter(
                                (f) => f.fieldId === field.id,
                              );
                              return (
                                <React.Fragment key={field.id}>
                                  <tr
                                    className={`field ${flags.length ? "flagged" : ""} ${selection?.pageId === page.id && selection.fieldId === field.id ? "selected-field" : ""}`}
                                    onClick={() =>
                                      setSelection({
                                        pageId: page.id,
                                        fieldId: field.id,
                                        token: Date.now(),
                                      })
                                    }
                                  >
                                    <td className="field-label">
                                      <button
                                        className="locate-field"
                                        aria-label={`Locate ${field.group}: ${field.label} in image`}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          setSelection({
                                            pageId: page.id,
                                            fieldId: field.id,
                                            token: Date.now(),
                                          });
                                        }}
                                      >
                                        {field.label}
                                      </button>
                                    </td>
                                    <td>
                                      <div className="value-cell">
                                        <span
                                          className={
                                            page.type === "notes"
                                              ? "notes-value"
                                              : "value"
                                          }
                                        >
                                          {(pageReviews[field.id]
                                            ? pageReviews[field.id].value
                                            : field.value) || "–"}
                                        </span>
                                        <button
                                          className="edit-button"
                                          disabled={saving}
                                          onClick={() => beginEdit(field)}
                                          aria-label={`Edit ${field.label}`}
                                          title="Edit or review this field"
                                        >
                                          <Pencil size={15} />
                                        </button>
                                      </div>
                                    </td>
                                    <td>
                                      {flags.length ? (
                                        <details className="flag-details">
                                          <summary>
                                            <TriangleAlert size={18} />
                                            <span>
                                              {[...new Set(flags.map((flag) => flagLabels[flag.kind]))].join(", ")}
                                            </span>
                                          </summary>
                                          {flags.map((flag) => (
                                            <div
                                              className="flag-reason"
                                              key={flag.id}
                                            >
                                              <strong>
                                                {flagLabels[flag.kind]}
                                              </strong>
                                              <p>{flag.reason}</p>
                                            </div>
                                          ))}
                                        </details>
                                      ) : (
                                        "—"
                                      )}
                                    </td>
                                    <td>
                                      <span className="field-status">
                                        {pageReviews[field.id]
                                          ? `${pageReviews[field.id].savedAt ? "Reviewed" : "Unsaved"} by: ${pageReviews[field.id].reviewer}`
                                          : field.value === null ||
                                              field.value === ""
                                            ? "Blank"
                                            : "Transcribed"}
                                      </span>
                                    </td>
                                  </tr>
                                </React.Fragment>
                              );
                            })}
                      </tbody>
                    ))}
                  </table>
                )}
              </div>
              <div className="panel-footer">
                {visible.length} of {page.fields.length} fields
              </div>
            </section>
            <section className="source">
              <div className="source-heading">
                <div>
                  <h2>Transcript Review</h2>
                  <nav className="pager" aria-label="Survey pages">
                    <button
                      aria-label="Previous page"
                      disabled={saving || index === 0}
                      onClick={() => navigate(index - 1)}
                    >
                      <ChevronLeft size={18} />
                    </button>
                    <span>
                      Page {index + 1} of {survey.pages.length}
                    </span>
                    <button
                      aria-label="Next page"
                      disabled={saving || index === survey.pages.length - 1}
                      onClick={() => navigate(index + 1)}
                    >
                      <ChevronRight size={18} />
                    </button>
                  </nav>
                </div>
                <button onClick={download}>
                  <Download size={16} /> Export{" "}
                </button>
              </div>
              <ImageViewer
                key={page.id}
                page={page}
                selection={selection?.pageId === page.id ? selection : null}
              />
              <div className="reviewer-controls">
                <label>
                  Reviewer name *
                  <select
                    aria-label="Reviewer name"
                    value={reviewer}
                    onChange={(e) => {
                      if (e.target.value === "__add__") {
                        setAdding(true);
                      } else setReviewer(e.target.value);
                    }}
                  >
                    <option value="">Select reviewer</option>
                    {reviewers.map((person) => (
                      <option key={person.id} value={person.name}>
                        {person.name}
                      </option>
                    ))}
                    <option value="__add__">+ Add reviewer…</option>
                  </select>
                </label>
                <button onClick={() => setAdding((a) => !a)}>
                  Add reviewer
                </button>
                <button
                  disabled={saving || !reviewer || !page.fields.length}
                  onClick={reviewAll}
                >
                  Reviewed all fields on page
                </button>
                <button
                  disabled={
                    saving ||
                    !reviewer ||
                    !Object.values(pageReviews).some((e) => !e.savedAt)
                  }
                  onClick={savePage}
                >
                  {saving ? "Saving…" : "Save Page Transcript"}
                </button>
              </div>
              {adding && (
                <form
                  className="add-reviewer"
                  onSubmit={(e) => {
                    e.preventDefault();
                    addReviewer();
                  }}
                >
                  <input
                    autoFocus
                    aria-label="New reviewer name"
                    placeholder="Enter reviewer name"
                    maxLength={80}
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                  <button disabled={!newName.trim()} type="submit">
                    Add
                  </button>
                  <button type="button" onClick={() => setAdding(false)}>
                    Cancel
                  </button>
                </form>
              )}
              <p className="save-help" role="status">
                {message ||
                  "Reviews are saved in this browser. Select a reviewer before applying an edit."}
              </p>
            </section>
          </div>
        )}
      </main>
      <dialog
        ref={navigationDialog}
        className="edit-dialog"
        aria-labelledby="unsaved-reviews-heading"
        onCancel={(event) => {
          event.preventDefault();
          stayOnPage();
        }}
      >
        <h2 id="unsaved-reviews-heading">Save your reviews before leaving?</h2>
        <p>
          This page has unsaved reviews. Save them or discard them before
          continuing.
        </p>
        <p>
          Discarding restores the last saved values. Previously saved reviews
          are kept.
        </p>
        <div className="dialog-actions">
          <button autoFocus disabled={saving} onClick={stayOnPage}>
            Stay here
          </button>
          <button disabled={saving} onClick={discardAndContinue}>
            Discard reviews and continue
          </button>
          <button disabled={saving || !reviewer} onClick={saveAndContinue}>
            {saving ? "Saving…" : "Save and continue"}
          </button>
        </div>
        <p role="status">{message}</p>
      </dialog>
      <dialog
        ref={editor}
        className="edit-dialog"
        onCancel={() => setEditing(null)}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            applyEdit();
          }}
        >
          <h2>Edit field</h2>
          {/* Explain each flag on the selected field before the reviewer edits it. */}
          {page?.flags.filter((flag) => flag.fieldId === editing?.id).map((flag) => (
            <div className="flag-reason" key={flag.id}>
              <strong>{flagLabels[flag.kind]}</strong>
              <p>{flag.reason}</p>
            </div>
          ))}
          <p className="edit-context">
            {page && names[page.type]} · {editing?.label}
          </p>
          <label>
            Extracted value
            <div className="original-value">{editing?.value || "Blank"}</div>
          </label>
          <label htmlFor="field-value">Reviewed value</label>
          <textarea
            autoFocus
            id="field-value"
            rows={page?.type === "notes" ? 10 : 4}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
          />
          <p className="edit-help">
            Leave empty to record a blank value. Existing flags remain for
            checking.
          </p>
          <label htmlFor="edit-reviewer">Reviewer *</label>
          <select
            id="edit-reviewer"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
          >
            <option value="">Select reviewer</option>
            {reviewers.map((person) => (
              <option key={person.id} value={person.name}>
                {person.name}
              </option>
            ))}
          </select>
          {!reviewers.length && (
            <p className="edit-help">
              Close this window and use Add reviewer below the scan first.
            </p>
          )}
          <div className="dialog-actions">
            <button
              type="button"
              onClick={() => {
                editor.current?.close();
                setEditing(null);
              }}
            >
              Cancel
            </button>
            <button type="submit" disabled={!reviewer}>
              Apply review
            </button>
          </div>
          <p className="edit-help">
            Applying a review creates an unsaved change. Save the page to keep
            it in this browser.
          </p>
        </form>
      </dialog>
    </>
  );
}
