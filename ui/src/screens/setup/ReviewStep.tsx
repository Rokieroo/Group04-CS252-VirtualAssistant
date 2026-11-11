import { useState } from "react";
import type { SyllabusDraft } from "../../api/core";
import { manuallyReviewable, warningKey } from "../../api/syllabus";
import type { Course } from "../../app/useCourse";
import { Button, Dialog, Field, IconButton, Notice, Tabs } from "../../ui/kit";

type Sections = Pick<SyllabusDraft, "outcomes" | "weeks" | "assessments" | "textbooks">;
type Section = keyof Sections;

const sectionLabels: Record<Section, string> = {
  outcomes: "Chuẩn đầu ra",
  weeks: "Tuần và chủ đề",
  assessments: "Đánh giá",
  textbooks: "Giáo trình",
};
const courseFields = [
  ["code", "Mã môn"],
  ["title", "Tên môn"],
  ["credits", "Số tín chỉ"],
  ["language", "Ngôn ngữ"],
  ["term_start", "Ngày bắt đầu học kỳ"],
  ["term_end", "Ngày kết thúc học kỳ"],
] as const;
const bloom = [
  ["remember", "Nhớ"],
  ["understand", "Hiểu"],
  ["apply", "Vận dụng"],
  ["analyze", "Phân tích"],
  ["evaluate", "Đánh giá"],
  ["create", "Sáng tạo"],
] as const;
const kinds = [
  ["quiz", "Kiểm tra ngắn"],
  ["midterm", "Giữa kỳ"],
  ["final", "Cuối kỳ"],
  ["project", "Đồ án"],
  ["homework", "Bài tập"],
  ["other", "Khác"],
] as const;

/** "weeks.2" → the tab it lives on and a name a learner recognises. */
function locate(path = ""): { section?: Section; label: string } {
  const [head, index] = path.split(".");
  const row = index === undefined ? "" : `, dòng ${Number(index) + 1}`;
  if (head in sectionLabels) return { section: head as Section, label: sectionLabels[head as Section] + row };
  return { label: head === "course" ? "Thông tin môn học" : "" };
}

/** Step 2 (S4): everything read from the syllabus, editable, each value next to its source page. */
export function ReviewStep({ course }: { course: Course }) {
  const { draft, update, warnings, blocked, busy } = course;
  const [tab, setTab] = useState<Section>("outcomes");
  const [page, setPage] = useState<number | null>(null);
  if (!draft) return null;

  // Rows have no ids, so a row is addressed by its index in its section.
  const edit = <K extends Section>(key: K, index: number, change: Partial<Sections[K][number]>) =>
    update({
      [key]: (draft[key] as Sections[K][number][]).map((row, i) =>
        i === index ? { ...row, ...change } : row,
      ),
    });
  const remove = (key: Section, index: number) =>
    update({ [key]: (draft[key] as unknown[]).filter((_, i) => i !== index) });
  const cite = (source?: number) =>
    source ? (
      <button type="button" className="cite" onClick={() => setPage(source)}>
        tr. {source}
      </button>
    ) : (
      <span className="cite-none">Không có trang nguồn</span>
    );
  const drop = (key: Section, index: number, name: string) => (
    <IconButton icon="trash" label={`Xóa ${name}`} onClick={() => remove(key, index)} />
  );

  const blocking = warnings.filter((w) => w.blocking);
  const weightTotal = draft.assessments.reduce((sum, a) => sum + (Number(a.weight) || 0), 0);

  return (
    <div className="review">
      <fieldset disabled={busy} aria-busy={busy} className="stack">
        <p className="muted">
          {draft.file_name}
          {draft.pages ? `, ${draft.pages} trang` : ""}. Bấm vào số trang cạnh mỗi mục để đối chiếu
          với bản gốc.
        </p>

        {warnings.length > 0 && (
          <section className="warnings" aria-label="Điểm cần kiểm tra">
            <h2>
              {blocking.length
                ? `${blocking.length} điểm cần sửa trước khi tiếp tục`
                : "Vài điểm nên xem lại"}
            </h2>
            <ul>
              {warnings.map((w, i) => {
                const where = locate(w.path);
                return (
                  <li key={warningKey(w) + i} className={w.blocking ? "warning-blocking" : ""}>
                    <div className="grow">
                      <p>
                        {where.label && <strong>{where.label}: </strong>}
                        {w.message}
                      </p>
                      {manuallyReviewable.has(w.code) && (
                        <label className="check small">
                          <input
                            type="checkbox"
                            onChange={() =>
                              update({
                                reviewed_warnings: [...(draft.reviewed_warnings ?? []), warningKey(w)],
                              })
                            }
                          />
                          <span>Tôi đã đối chiếu trang nguồn và nhập lại phần thiếu hoặc sai.</span>
                        </label>
                      )}
                    </div>
                    {where.section && where.section !== tab && (
                      <Button size="sm" variant="quiet" onClick={() => setTab(where.section!)}>
                        Mở mục này
                      </Button>
                    )}
                  </li>
                );
              })}
            </ul>
          </section>
        )}

        <details className="fold">
          <summary>Thông tin môn học</summary>
          <div className="form-grid fold-body">
            {courseFields.map(([key, label]) => (
              <div className="cited" key={key}>
                <Field label={label}>
                  <input
                    type={key.startsWith("term_") ? "date" : "text"}
                    value={draft.course?.[key]?.value ?? ""}
                    onChange={(event) =>
                      update({
                        course: {
                          ...draft.course,
                          [key]: { ...draft.course?.[key], value: event.target.value },
                        },
                      })
                    }
                  />
                </Field>
                {cite(draft.course?.[key]?.source_page)}
              </div>
            ))}
          </div>
        </details>

        <Tabs
          label="Các phần của đề cương"
          panelId="review-panel"
          value={tab}
          onChange={setTab}
          tabs={(Object.keys(sectionLabels) as Section[]).map((id) => ({
            id,
            label: sectionLabels[id],
            count: draft[id].length,
          }))}
        />

        <div role="tabpanel" id="review-panel" aria-labelledby={`review-panel-tab-${tab}`} className="rows">
          {tab === "outcomes" && (
            <>
              {draft.outcomes.map((o, i) => (
                <div className="edit-row row-outcome" key={i}>
                  <Field label="Mã">
                    <input value={o.code} onChange={(e) => edit("outcomes", i, { code: e.target.value })} />
                  </Field>
                  <Field label="Nội dung chuẩn đầu ra">
                    <input
                      value={o.description}
                      onChange={(e) => edit("outcomes", i, { description: e.target.value })}
                    />
                  </Field>
                  <Field label="Mức độ">
                    <select
                      value={o.bloom_level ?? "understand"}
                      onChange={(e) => edit("outcomes", i, { bloom_level: e.target.value })}
                    >
                      {bloom.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <div className="row-tools">
                    {cite(o.source_page)}
                    {drop("outcomes", i, o.code || `chuẩn đầu ra ${i + 1}`)}
                  </div>
                </div>
              ))}
              <Button
                icon="plus"
                onClick={() =>
                  update({
                    outcomes: [
                      ...draft.outcomes,
                      { code: `CLO${draft.outcomes.length + 1}`, description: "" },
                    ],
                  })
                }
              >
                Thêm chuẩn đầu ra
              </Button>
            </>
          )}

          {tab === "weeks" && (
            <>
              {draft.weeks.map((w, i) => (
                <div className="edit-row row-week" key={i}>
                  <Field label="Tuần">
                    <input
                      type="number"
                      min="1"
                      value={w.week}
                      onChange={(e) => edit("weeks", i, { week: Number(e.target.value) })}
                    />
                  </Field>
                  <Field label="Chủ đề" hint="Cách nhau bằng dấu phẩy">
                    <input
                      value={w.topics.join(", ")}
                      onChange={(e) =>
                        edit("weeks", i, { topics: e.target.value.split(",").map((s) => s.trim()) })
                      }
                    />
                  </Field>
                  <Field label="Bài đọc" hint="Mỗi dòng một mục">
                    <textarea
                      rows={2}
                      value={(w.readings ?? []).join("\n")}
                      onChange={(e) => edit("weeks", i, { readings: e.target.value.split("\n") })}
                    />
                  </Field>
                  <div className="row-tools">
                    <label className="check small">
                      <input
                        type="checkbox"
                        checked={w.estimated ?? false}
                        onChange={(e) => edit("weeks", i, { estimated: e.target.checked })}
                      />
                      <span>Tuần ước lượng</span>
                    </label>
                    {cite(w.source_page)}
                    {drop("weeks", i, `tuần ${w.week}`)}
                  </div>
                </div>
              ))}
              <Button
                icon="plus"
                onClick={() =>
                  update({ weeks: [...draft.weeks, { week: draft.weeks.length + 1, topics: [""] }] })
                }
              >
                Thêm tuần
              </Button>
            </>
          )}

          {tab === "assessments" && (
            <>
              <p className={`small ${weightTotal === 100 ? "muted" : "weight-off"}`}>
                Tổng trọng số: {weightTotal}%
              </p>
              {draft.assessments.map((a, i) => (
                <div className="edit-row row-assessment" key={i}>
                  <Field label="Tên bài đánh giá">
                    <input value={a.name} onChange={(e) => edit("assessments", i, { name: e.target.value })} />
                  </Field>
                  <Field label="Trọng số (%)">
                    <input
                      type="number"
                      min="0"
                      max="100"
                      value={a.weight}
                      onChange={(e) => edit("assessments", i, { weight: Number(e.target.value) })}
                    />
                  </Field>
                  <Field label="Tuần">
                    <input
                      type="number"
                      min="1"
                      value={a.due_week ?? ""}
                      onChange={(e) =>
                        edit("assessments", i, { due_week: Number(e.target.value) || null, due_date: "" })
                      }
                    />
                  </Field>
                  <Field label="Hoặc ngày hạn">
                    <input
                      type="date"
                      value={a.due_date ?? ""}
                      onChange={(e) =>
                        edit("assessments", i, {
                          due_date: e.target.value,
                          due_week: e.target.value ? null : a.due_week,
                        })
                      }
                    />
                  </Field>
                  <Field label="Loại">
                    <select
                      value={a.kind ?? "other"}
                      onChange={(e) => edit("assessments", i, { kind: e.target.value })}
                    >
                      {kinds.map(([value, label]) => (
                        <option key={value} value={value}>
                          {label}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <div className="row-tools">
                    {cite(a.source_page)}
                    {drop("assessments", i, a.name || `bài đánh giá ${i + 1}`)}
                  </div>
                </div>
              ))}
              <Button
                icon="plus"
                onClick={() =>
                  update({ assessments: [...draft.assessments, { name: "", weight: 0, due_week: null }] })
                }
              >
                Thêm bài đánh giá
              </Button>
            </>
          )}

          {tab === "textbooks" && (
            <>
              {draft.textbooks.map((b, i) => (
                <div className="edit-row row-book" key={i}>
                  <Field label="Tên giáo trình">
                    <input value={b.title} onChange={(e) => edit("textbooks", i, { title: e.target.value })} />
                  </Field>
                  <Field label="Tác giả">
                    <input value={b.author} onChange={(e) => edit("textbooks", i, { author: e.target.value })} />
                  </Field>
                  <Field label="Bắt buộc">
                    <select
                      value={b.required === undefined ? "unknown" : String(b.required)}
                      onChange={(e) =>
                        edit("textbooks", i, {
                          required: e.target.value === "unknown" ? undefined : e.target.value === "true",
                        })
                      }
                    >
                      <option value="unknown">Chưa rõ</option>
                      <option value="true">Có</option>
                      <option value="false">Không</option>
                    </select>
                  </Field>
                  <div className="row-tools">
                    {cite(b.source_page)}
                    {drop("textbooks", i, b.title || `giáo trình ${i + 1}`)}
                  </div>
                </div>
              ))}
              <Button
                icon="plus"
                onClick={() => update({ textbooks: [...draft.textbooks, { title: "", author: "" }] })}
              >
                Thêm giáo trình
              </Button>
            </>
          )}
        </div>
      </fieldset>

      <div className="action-bar">
        <Button variant="quiet" disabled={busy} onClick={() => course.setStage("upload")}>
          Chọn đề cương khác
        </Button>
        <div className="row row-end grow">
          {blocked && <span className="muted small">Sửa các điểm được đánh dấu để tiếp tục.</span>}
          <Button variant="primary" disabled={blocked || busy} onClick={() => void course.confirmAndGenerate()}>
            {busy ? "Đang tạo lộ trình…" : "Xác nhận và tạo lộ trình"}
          </Button>
        </div>
      </div>

      {page !== null && (
        <Dialog
          title={`${draft.file_name}, trang ${page}`}
          onClose={() => setPage(null)}
          wide
          footer={<Button onClick={() => setPage(null)}>Đóng</Button>}
        >
          <p className="pre">
            {draft.source_pages?.[page] || "Chưa có nội dung của trang nguồn này."}
          </p>
        </Dialog>
      )}
      {course.error && !busy && <Notice tone="error">{course.error}</Notice>}
    </div>
  );
}
