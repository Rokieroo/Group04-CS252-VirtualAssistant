import { useState, type ReactNode } from "react";
import type { SyllabusDraft, Warning } from "../../api/core";
type ReviewTab = "outcomes" | "weeks" | "assessments" | "textbooks";
const tabs: { id: ReviewTab; label: string }[] = [
  { id: "outcomes", label: "Chuẩn đầu ra" },
  { id: "weeks", label: "Tuần & chủ đề" },
  { id: "assessments", label: "Đánh giá" },
  { id: "textbooks", label: "Giáo trình" },
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
  const [reviewTab, setReviewTab] = useState<ReviewTab>("outcomes");
  return (
    <section className="card core-panel" aria-labelledby="s4-title">
      <div>
        <span className="core-kicker">S4 · Kiểm tra</span>
        <h2 id="s4-title">Duyệt đề cương</h2>
        <p>Sửa từng phần trước khi xác nhận.</p>
      </div>
      {warnings.length > 0 && (
        <div className="core-warning" role="alert">
          {warnings.map((w, i) => (
            <p key={`${w.code}-${i}`}>{w.message}</p>
          ))}
        </div>
      )}
      <div className="core-tabs" role="tablist" aria-label="Các phần đề cương">
        {tabs.map((t) => (
          <button
            key={t.id}
            role="tab"
            aria-selected={reviewTab === t.id}
            onClick={() => setReviewTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="core-review-columns">
        <div role="tabpanel" className="core-fields">
          {reviewTab === "outcomes" && (
            <>
              {draft?.outcomes.map((o, i) => (
                <div className="core-row" key={i}>
                  <label>
                    Mã CLO
                    <input
                      value={o.code}
                      onChange={(e) =>
                        update({
                          outcomes: draft.outcomes.map((x, j) =>
                            i === j ? { ...x, code: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    Mục tiêu
                    <input
                      value={o.description}
                      onChange={(e) =>
                        update({
                          outcomes: draft.outcomes.map((x, j) =>
                            i === j ? { ...x, description: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </label>
                  {sourceChip(o.source_page)}
                  <button
                    onClick={() =>
                      update({
                        outcomes: draft.outcomes.filter((_, j) => j !== i),
                      })
                    }
                  >
                    Xóa
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
                + Thêm chuẩn đầu ra
              </button>
            </>
          )}
          {reviewTab === "weeks" && (
            <>
              {draft?.weeks.map((w, i) => (
                <div className="core-row" key={i}>
                  <label>
                    Tuần
                    <input
                      type="number"
                      min="1"
                      value={w.week}
                      onChange={(e) =>
                        update({
                          weeks: draft.weeks.map((x, j) =>
                            j === i
                              ? { ...x, week: Number(e.target.value) }
                              : x,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    Chủ đề (cách nhau bằng dấu phẩy)
                    <input
                      value={w.topics.join(", ")}
                      onChange={(e) =>
                        update({
                          weeks: draft.weeks.map((x, j) =>
                            j === i
                              ? {
                                  ...x,
                                  topics: e.target.value
                                    .split(",")
                                    .map((s) => s.trim()),
                                }
                              : x,
                          ),
                        })
                      }
                    />
                  </label>
                  {sourceChip(w.source_page)}
                  <button
                    onClick={() =>
                      update({ weeks: draft.weeks.filter((_, j) => j !== i) })
                    }
                  >
                    Xóa
                  </button>
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
                + Thêm tuần
              </button>
            </>
          )}
          {reviewTab === "assessments" && (
            <>
              {draft?.assessments.map((a, i) => (
                <div className="core-row" key={i}>
                  <label>
                    Tên đánh giá
                    <input
                      value={a.name}
                      onChange={(e) =>
                        update({
                          assessments: draft.assessments.map((x, j) =>
                            j === i ? { ...x, name: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    Trọng số %
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={a.weight}
                      onChange={(e) =>
                        update({
                          assessments: draft.assessments.map((x, j) =>
                            j === i
                              ? { ...x, weight: Number(e.target.value) }
                              : x,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    Tuần
                    <input
                      type="number"
                      min="1"
                      value={a.due_week ?? ""}
                      onChange={(e) =>
                        update({
                          assessments: draft.assessments.map((x, j) =>
                            j === i
                              ? {
                                  ...x,
                                  due_week: Number(e.target.value) || null,
                                }
                              : x,
                          ),
                        })
                      }
                    />
                  </label>
                  {sourceChip(a.source_page)}
                  <button
                    onClick={() =>
                      update({
                        assessments: draft.assessments.filter(
                          (_, j) => j !== i,
                        ),
                      })
                    }
                  >
                    Xóa
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
                + Thêm đánh giá
              </button>
            </>
          )}
          {reviewTab === "textbooks" && (
            <>
              {draft?.textbooks.map((b, i) => (
                <div className="core-row" key={i}>
                  <label>
                    Tên giáo trình
                    <input
                      value={b.title}
                      onChange={(e) =>
                        update({
                          textbooks: draft.textbooks.map((x, j) =>
                            j === i ? { ...x, title: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </label>
                  <label>
                    Tác giả
                    <input
                      value={b.author}
                      onChange={(e) =>
                        update({
                          textbooks: draft.textbooks.map((x, j) =>
                            j === i ? { ...x, author: e.target.value } : x,
                          ),
                        })
                      }
                    />
                  </label>
                  {sourceChip(b.source_page)}
                  <button
                    onClick={() =>
                      update({
                        textbooks: draft.textbooks.filter((_, j) => j !== i),
                      })
                    }
                  >
                    Xóa
                  </button>
                </div>
              ))}
              <button
                onClick={() =>
                  draft &&
                  update({
                    textbooks: [...draft.textbooks, { title: "", author: "" }],
                  })
                }
              >
                + Thêm giáo trình
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
          Máy chủ hiện chỉ lưu chuẩn đầu ra, đánh giá và văn bản gốc. Tuần, giáo
          trình và trang nguồn chỉ hiện trong phiên này.
        </p>
      )}
      <div className="core-actions">
        <button onClick={() => onBack()}>Tải lại</button>
        <button
          className="primary-action"
          disabled={blocked || busy || draft?.status === "confirmed"}
          onClick={confirm}
        >
          {draft?.status === "confirmed" ? "Đã xác nhận" : "Xác nhận đề cương"}
        </button>
        <button
          disabled={draft?.status !== "confirmed" || busy}
          onClick={generate}
        >
          Tạo roadmap →
        </button>
      </div>
    </section>
  );
}
