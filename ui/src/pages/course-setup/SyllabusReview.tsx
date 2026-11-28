import { TabList, Tab } from "@astryxdesign/core/TabList";
import { manuallyReviewable, warningKey } from "../../api/syllabus";
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { SyllabusDraft, Warning } from "../../api/core";
type Sections = Pick<
  SyllabusDraft,
  "outcomes" | "weeks" | "assessments" | "textbooks"
>;
type ReviewTab = keyof Sections;
const tabs: { id: ReviewTab; label: string }[] = [
  { id: "outcomes", label: "Learning outcomes" },
  { id: "weeks", label: "Weeks & topics" },
  { id: "assessments", label: "Assessments" },
  { id: "textbooks", label: "Textbooks" },
];

type Props = {
  draft: SyllabusDraft;
  update: (change: Partial<SyllabusDraft>) => void;
  warnings: Warning[];
  blocked: boolean;
  busy: boolean;
  mock: boolean;
  confirm: () => void;
  generate: () => void;
  onBack: () => void;
  sourceChip: (page?: number) => ReactNode;
};
export function SyllabusReview({
  draft,
  update,
  warnings,
  blocked,
  busy,
  mock,
  confirm,
  generate,
  onBack,
  sourceChip,
}: Props) {
  const nextStep = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (draft.status === "confirmed" && !busy) nextStep.current?.focus();
  }, [draft.status, busy]);
  const [reviewTab, setReviewTab] = useState<ReviewTab>("outcomes");
  // Rows have no ids, so a row is addressed by its index in its section.
  const editRow = <K extends ReviewTab>(
    key: K,
    index: number,
    change: Partial<Sections[K][number]>,
  ) =>
    update({
      [key]: (draft[key] as Sections[K][number][]).map((row, j) =>
        j === index ? { ...row, ...change } : row,
      ),
    });
  const removeRow = (key: ReviewTab, index: number) =>
    update({
      [key]: (draft[key] as Sections[ReviewTab][number][]).filter(
        (_, j) => j !== index,
      ),
    });
  return (
    <section className="card core-panel" aria-labelledby="s4-title">
      <fieldset aria-busy={busy} disabled={busy} className="core-review-form">
        <div>
          <span className="core-kicker">S4 · Review</span>
          <h2 id="s4-title">Review syllabus</h2>
          <p>Edit each section before confirming.</p>
        </div>
        {warnings.length > 0 && (
          <div className="core-warning" role="alert">
            {warnings.map((w, i) => (
              <div key={warningKey(w) + i}>
                <p>
                  {w.path && <strong>{w.path}: </strong>}
                  {w.message}
                </p>
                {manuallyReviewable.has(w.code) && (
                  <label>
                    <input
                      type="checkbox"
                      onChange={() =>
                        update({
                          reviewed_warnings: [
                            ...(draft.reviewed_warnings ?? []),
                            warningKey(w),
                          ],
                        })
                      }
                    />
                    I have checked the source page and corrected any missing or
                    inaccurate content.
                  </label>
                )}
              </div>
            ))}
          </div>
        )}
        <details>
          <summary>Course information</summary>
          <div className="core-fields">
            {[
              "code",
              "title",
              "credits",
              "term_start",
              "term_end",
              "language",
            ].map((key) => (
              <label key={key}>
                {
                  {
                    code: "Course code",
                    title: "Course title",
                    credits: "Credits",
                    term_start: "Start date",
                    term_end: "End date",
                    language: "Language",
                  }[key]
                }
                <input
                  type={key.startsWith("term_") ? "date" : "text"}
                  value={draft.course?.[key]?.value ?? ""}
                  onChange={(e) =>
                    update({
                      course: {
                        ...draft.course,
                        [key]: {
                          ...draft.course?.[key],
                          value: e.target.value,
                        },
                      },
                    })
                  }
                />
                {sourceChip(draft.course?.[key]?.source_page)}
              </label>
            ))}
          </div>
        </details>
        <TabList
          className="study-tabs"
          role="tablist"
          aria-label="Syllabus sections"
          size="lg"
          hasDivider
          value={reviewTab}
          onChange={(value) => setReviewTab(value as ReviewTab)}
        >
          {tabs.map((t) => (
            <Tab
              key={t.id}
              value={t.id}
              label={t.label}
              id={`review-tab-${t.id}`}
              panelId="review-panel"
              onFocusCapture={() => setReviewTab(t.id)}
            />
          ))}
        </TabList>
        <div className="core-review-columns">
          <div
            role="tabpanel"
            id="review-panel"
            aria-labelledby={`review-tab-${reviewTab}`}
            className="core-fields"
          >
            {reviewTab === "outcomes" && (
              <>
                {draft?.outcomes.map((o, i) => (
                  <div className="core-row" key={i}>
                    <label>
                      CLO code
                      <input
                        value={o.code}
                        onChange={(e) =>
                          editRow("outcomes", i, { code: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Outcome description
                      <input
                        value={o.description}
                        onChange={(e) =>
                          editRow("outcomes", i, {
                            description: e.target.value,
                          })
                        }
                      />
                    </label>
                    <label>
                      Bloom level
                      <select
                        value={o.bloom_level ?? "understand"}
                        onChange={(e) =>
                          editRow("outcomes", i, {
                            bloom_level: e.target.value,
                          })
                        }
                      >
                        {[
                          "remember",
                          "understand",
                          "apply",
                          "analyze",
                          "evaluate",
                          "create",
                        ].map((level) => (
                          <option key={level}>{level}</option>
                        ))}
                      </select>
                    </label>
                    {sourceChip(o.source_page)}
                    <button onClick={() => removeRow("outcomes", i)}>
                      Delete
                    </button>
                  </div>
                ))}
                <button
                  onClick={() =>
                    draft &&
                    update({
                      outcomes: [
                        ...draft.outcomes,
                        {
                          code: `CLO${draft.outcomes.length + 1}`,
                          description: "",
                        },
                      ],
                    })
                  }
                >
                  + Add learning outcome
                </button>
              </>
            )}
            {reviewTab === "weeks" && (
              <>
                {draft?.weeks.map((w, i) => (
                  <div className="core-row" key={i}>
                    <label>
                      Week
                      <input
                        type="number"
                        min="1"
                        value={w.week}
                        onChange={(e) =>
                          editRow("weeks", i, { week: Number(e.target.value) })
                        }
                      />
                    </label>
                    <label>
                      Topics (comma-separated)
                      <input
                        value={w.topics.join(", ")}
                        onChange={(e) =>
                          editRow("weeks", i, {
                            topics: e.target.value
                              .split(",")
                              .map((s) => s.trim()),
                          })
                        }
                      />
                    </label>
                    <label>
                      Readings (one per line)
                      <textarea
                        value={(w.readings ?? []).join("\n")}
                        onChange={(e) =>
                          editRow("weeks", i, {
                            readings: e.target.value.split("\n"),
                          })
                        }
                      />
                    </label>
                    <label>
                      <input
                        type="checkbox"
                        checked={w.estimated ?? false}
                        onChange={(e) =>
                          editRow("weeks", i, { estimated: e.target.checked })
                        }
                      />
                      Estimated week
                    </label>
                    {sourceChip(w.source_page)}
                    <button onClick={() => removeRow("weeks", i)}>Delete</button>
                  </div>
                ))}
                <button
                  onClick={() =>
                    draft &&
                    update({
                      weeks: [
                        ...draft.weeks,
                        { week: draft.weeks.length + 1, topics: [""] },
                      ],
                    })
                  }
                >
                  + Add week
                </button>
              </>
            )}
            {reviewTab === "assessments" && (
              <>
                {draft?.assessments.map((a, i) => (
                  <div className="core-row" key={i}>
                    <label>
                      Assessment name
                      <input
                        value={a.name}
                        onChange={(e) =>
                          editRow("assessments", i, { name: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Weight %
                      <input
                        type="number"
                        min="0"
                        max="100"
                        value={a.weight}
                        onChange={(e) =>
                          editRow("assessments", i, {
                            weight: Number(e.target.value),
                          })
                        }
                      />
                    </label>
                    <label>
                      Week
                      <input
                        type="number"
                        min="1"
                        value={a.due_week ?? ""}
                        onChange={(e) =>
                          editRow("assessments", i, {
                            due_week: Number(e.target.value) || null,
                            due_date: "",
                          })
                        }
                      />
                    </label>
                    <label>
                      Due date (instead of week)
                      <input
                        type="date"
                        value={a.due_date ?? ""}
                        onChange={(e) =>
                          editRow("assessments", i, {
                            due_date: e.target.value,
                            due_week: e.target.value ? null : a.due_week,
                          })
                        }
                      />
                    </label>
                    <label>
                      Type
                      <select
                        value={a.kind ?? "other"}
                        onChange={(e) =>
                          editRow("assessments", i, { kind: e.target.value })
                        }
                      >
                        {[
                          "quiz",
                          "midterm",
                          "final",
                          "project",
                          "homework",
                          "other",
                        ].map((kind) => (
                          <option key={kind}>{kind}</option>
                        ))}
                      </select>
                    </label>
                    {sourceChip(a.source_page)}
                    <button onClick={() => removeRow("assessments", i)}>
                      Delete
                    </button>
                  </div>
                ))}
                <button
                  onClick={() =>
                    draft &&
                    update({
                      assessments: [
                        ...draft.assessments,
                        { name: "", weight: 0, due_week: null },
                      ],
                    })
                  }
                >
                  + Add assessment
                </button>
              </>
            )}
            {reviewTab === "textbooks" && (
              <>
                {draft?.textbooks.map((b, i) => (
                  <div className="core-row" key={i}>
                    <label>
                      Textbook title
                      <input
                        value={b.title}
                        onChange={(e) =>
                          editRow("textbooks", i, { title: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Author
                      <input
                        value={b.author}
                        onChange={(e) =>
                          editRow("textbooks", i, { author: e.target.value })
                        }
                      />
                    </label>
                    <label>
                      Required
                      <select
                        value={
                          b.required === undefined
                            ? "unknown"
                            : String(b.required)
                        }
                        onChange={(e) =>
                          editRow("textbooks", i, {
                            required:
                              e.target.value === "unknown"
                                ? undefined
                                : e.target.value === "true",
                          })
                        }
                      >
                        <option value="unknown">Unknown</option>
                        <option value="true">Yes</option>
                        <option value="false">No</option>
                      </select>
                    </label>
                    {sourceChip(b.source_page)}
                    <button onClick={() => removeRow("textbooks", i)}>
                      Delete
                    </button>
                  </div>
                ))}
                <button
                  onClick={() =>
                    draft &&
                    update({
                      textbooks: [
                        ...draft.textbooks,
                        { title: "", author: "" },
                      ],
                    })
                  }
                >
                  + Add textbook
                </button>
              </>
            )}
          </div>
          <aside className="core-review-evidence">
            <h3>Source evidence</h3>
            <p>{draft.file_name}</p>
            <p>{draft.pages ? draft.pages + " pages" : "Pasted syllabus"}</p>
            <p>
              Select a page reference beside an extracted item to check the
              original text.
            </p>
            <dl>
              <dt>Learning outcomes</dt>
              <dd>{draft.outcomes.length}</dd>
              <dt>Weeks</dt>
              <dd>{draft.weeks.length}</dd>
              <dt>Assessments</dt>
              <dd>{draft.assessments.length}</dd>
              <dt>Textbooks</dt>
              <dd>{draft.textbooks.length}</dd>
            </dl>
          </aside>
        </div>
        {!mock && (
          <p className="hint">
            All reviewed fields and source pages are saved upon confirmation.
          </p>
        )}
        {draft.status === "confirmed" && (
          <p role="status">
            Syllabus review saved. You can now generate your roadmap.
          </p>
        )}
        <div className="core-actions">
          <button onClick={() => onBack()}>Re-upload</button>
          <button
            className="primary-action"
            disabled={blocked || busy || draft?.status === "confirmed"}
            onClick={confirm}
          >
            {draft?.status === "confirmed"
              ? "Confirmed"
              : "Confirm syllabus"}
          </button>
          <button
            disabled={draft?.status !== "confirmed" || busy}
            ref={nextStep}
            onClick={generate}
          >
            Generate roadmap →
          </button>
        </div>
      </fieldset>
    </section>
  );
}
