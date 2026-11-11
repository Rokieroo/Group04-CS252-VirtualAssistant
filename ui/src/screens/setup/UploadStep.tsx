import { useRef, useState, type DragEvent } from "react";
import type { Course } from "../../app/useCourse";
import { Icon } from "../../ui/icons";
import { Button, Field } from "../../ui/kit";

/** Step 1 (S3): hand over the syllabus as a file or as text. Choosing and sending are separate acts. */
export function UploadStep({ course }: { course: Course }) {
  const picker = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [mode, setMode] = useState<"file" | "text">("file");
  const [text, setText] = useState("");
  const [goals, setGoals] = useState(false);
  const [over, setOver] = useState(false);
  const { busy } = course;

  const drop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    if (!busy && event.dataTransfer.files[0]) setFile(event.dataTransfer.files[0]);
  };
  const ready = mode === "file" ? Boolean(file) : Boolean(text.trim());
  const send = () => {
    if (mode === "file" && file) void course.upload(file);
    else if (mode === "text" && text.trim()) void course.upload(text, { goals });
  };

  return (
    <form
      className="upload"
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
    >
      <div className="segmented" role="group" aria-label="Cách đưa đề cương vào">
        <button type="button" aria-pressed={mode === "file"} disabled={busy} onClick={() => setMode("file")}>
          Tải tệp lên
        </button>
        <button type="button" aria-pressed={mode === "text"} disabled={busy} onClick={() => setMode("text")}>
          Dán nội dung
        </button>
      </div>

      {mode === "file" ? (
        <div
          className={`drop ${over ? "drop-over" : ""} ${file ? "drop-filled" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            setOver(true);
          }}
          onDragLeave={(event) => {
            if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOver(false);
          }}
          onDrop={drop}
        >
          <input
            ref={picker}
            type="file"
            hidden
            accept=".pdf,.docx"
            aria-label="Tệp đề cương"
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              event.target.value = "";
            }}
          />
          {file ? (
            <>
              <span className="drop-icon">
                <Icon name="file" size={24} />
              </span>
              <strong className="drop-name">{file.name}</strong>
              <span className="muted small">{(file.size / 1024 / 1024).toFixed(1)} MB</span>
              <Button size="sm" disabled={busy} onClick={() => picker.current?.click()}>
                Chọn tệp khác
              </Button>
            </>
          ) : (
            <>
              <span className="drop-icon">
                <Icon name="upload" size={24} />
              </span>
              <strong>Kéo tệp đề cương vào đây</strong>
              <span className="muted small">PDF hoặc DOCX, tối đa 20 MB</span>
              <Button disabled={busy} onClick={() => picker.current?.click()}>
                Chọn tệp
              </Button>
            </>
          )}
        </div>
      ) : (
        <div className="stack">
          <Field
            label={goals ? "Mục tiêu học hoặc mục lục" : "Nội dung đề cương"}
            hint={
              goals
                ? "Mỗi dòng một mục tiêu hoặc một chương, ví dụ: Đệ quy, Sắp xếp, Cây nhị phân."
                : "Dán chuẩn đầu ra, chủ đề từng tuần và các bài đánh giá."
            }
          >
            <textarea
              rows={9}
              maxLength={120000}
              disabled={busy}
              value={text}
              onChange={(event) => setText(event.target.value)}
            />
          </Field>
          <label className="check">
            <input
              type="checkbox"
              disabled={busy}
              checked={goals}
              onChange={(event) => setGoals(event.target.checked)}
            />
            <span>Tôi không có đề cương. Đây là mục tiêu học hoặc mục lục của tôi.</span>
          </label>
        </div>
      )}

      {busy && <div className="progress-line" role="progressbar" aria-label="Đang đọc đề cương" />}

      <div className="row">
        <Button type="submit" variant="primary" disabled={busy || !ready}>
          {busy ? "Đang đọc đề cương…" : "Đọc đề cương"}
        </Button>
        <span className="muted small grow">
          {course.mock
            ? "Bản xem thử đọc tệp ngay trong trình duyệt bằng quy tắc đơn giản. Ứng dụng đầy đủ đọc bằng AI."
            : "Bạn sẽ kiểm tra và sửa mọi thứ trước khi lưu."}
        </span>
      </div>
    </form>
  );
}
