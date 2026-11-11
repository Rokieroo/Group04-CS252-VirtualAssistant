import { useEffect, useState } from "react";
import { call } from "../api/backend";

export type OwnedCourse = { id: string; title: string; level: string };
type SavedRoadmap = {
  id: string;
  title: string;
  created_at: string;
  nodes: { id: string }[];
};
const message = (e: unknown) =>
  e instanceof Error ? e.message : "Không thể tải dữ liệu.";

function CourseCard({
  course,
  onOpen,
}: {
  course: OwnedCourse;
  onOpen: (course: OwnedCourse, roadmapId?: string, resume?: boolean) => void;
}) {
  const [roadmaps, setRoadmaps] = useState<SavedRoadmap[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [expanded, setExpanded] = useState(false);
  useEffect(() => {
    if (!expanded) return;
    let cancelled = false;
    setLoading(true);
    setError("");
    call<SavedRoadmap[]>(`/courses/${encodeURIComponent(course.id)}/roadmaps`)
      .then((data) => {
        if (!cancelled) setRoadmaps(data);
      })
      .catch((e) => {
        if (!cancelled) setError(message(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [course.id, expanded, revision]);
  return (
    <article
      className="card core-panel course-library-card"
      aria-label={course.title}
    >
      <h2>{course.title}</h2>
      <p>
        Môn học cá nhân ·{" "}
        {course.level === "university"
          ? "Đại học"
          : course.level === "k12"
            ? "Phổ thông"
            : "Chưa xác định bậc học"}
      </p>
      <div className="core-actions">
        <button onClick={() => onOpen(course, undefined, true)}>
          Mở đề cương
        </button>
        <button onClick={() => onOpen(course, undefined, false)}>
          Thêm đề cương
        </button>
        <button aria-expanded={expanded} onClick={() => setExpanded(!expanded)}>
          Lộ trình đã lưu
        </button>
      </div>
      {expanded && (
        <div aria-busy={loading}>
          {loading && <p role="status">Đang tải lộ trình…</p>}
          {error && (
            <div role="alert">
              <p>{error}</p>
              <button onClick={() => setRevision(revision + 1)}>Thử lại</button>
            </div>
          )}
          {!loading && !error && roadmaps?.length === 0 && (
            <p>Chưa có lộ trình đã lưu. Mở đề cương để tiếp tục thiết lập.</p>
          )}
          {!loading && !error && !!roadmaps?.length && (
            <ul className="course-roadmap-list">
              {roadmaps.map((r) => (
                <li key={r.id}>
                  <div>
                    <strong>{r.title}</strong>
                    <p>
                      {r.nodes.length} chặng ·{" "}
                      <time dateTime={r.created_at}>
                        {new Date(r.created_at).toLocaleString("vi-VN")}
                      </time>
                    </p>
                  </div>
                  <button onClick={() => onOpen(course, r.id)}>
                    Mở lộ trình
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}

/** Personal courses from the signed-in account; never a prepared-course catalog. */
export function CourseLibrary({
  onOpen,
}: {
  onOpen: (course: OwnedCourse, roadmapId?: string, resume?: boolean) => void;
}) {
  const [courses, setCourses] = useState<OwnedCourse[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [createError, setCreateError] = useState("");
  const [title, setTitle] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError("");
    call<OwnedCourse[]>("/courses")
      .then((data) => {
        if (!cancelled) setCourses(data);
      })
      .catch((e) => {
        if (!cancelled) setError(message(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [revision]);
  return (
    <section
      className="core-journey course-library"
      aria-labelledby="my-courses-title"
    >
      <div>
        <span className="core-kicker">MÔN HỌC CỦA BẠN</span>
        <h1 id="my-courses-title">Tiếp tục hành trình học</h1>
        <p>Mở đề cương hoặc lộ trình đã lưu trong tài khoản của bạn.</p>
      </div>
      <form
        className="card core-panel"
        onSubmit={async (event) => {
          event.preventDefault();
          if (!title.trim() || creating) return;
          setCreating(true);
          setCreateError("");
          try {
            const course = await call<OwnedCourse>("/courses", {
              method: "POST",
              body: JSON.stringify({ title: title.trim() }),
            });
            setCourses((items) => [...items, course]);
            setTitle("");
            onOpen(course, undefined, false);
          } catch (e) {
            setCreateError(message(e));
          } finally {
            setCreating(false);
          }
        }}
      >
        <label>
          Tên môn học
          <input
            required
            maxLength={200}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            disabled={creating}
          />
        </label>
        <div className="core-actions">
          <button
            className="primary-action"
            disabled={creating || !title.trim()}
          >
            {creating ? "Đang tạo…" : "Tạo môn học"}
          </button>
        </div>
        {createError && <p role="alert">{createError}</p>}
      </form>
      {loading && <p role="status">Đang tải môn học…</p>}
      {error && (
        <div role="alert">
          <p>{error}</p>
          <button onClick={() => setRevision(revision + 1)}>Thử lại</button>
        </div>
      )}
      {!loading && !error && !courses.length && (
        <p>
          Chưa có môn học. Tạo môn đầu tiên rồi thêm đề cương hoặc mục tiêu học
          tập.
        </p>
      )}
      {!loading && !error && (
        <div className="course-library-grid">
          {courses.map((course) => (
            <CourseCard
              key={course.id + ":" + revision}
              course={course}
              onOpen={onOpen}
            />
          ))}
        </div>
      )}
      <button onClick={() => setRevision(revision + 1)} disabled={loading}>
        Làm mới danh sách
      </button>
    </section>
  );
}
