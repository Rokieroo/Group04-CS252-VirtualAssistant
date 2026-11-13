import { useEffect, useState } from "react";
import { fetchDueReviews, submitReview, type DueReviewCard } from "../api/reviews";
import type { Route } from "../app/routes";
import { explain } from "../app/text";
import type { Course, Stage } from "../app/useCourse";
import { Button, Chip, Dialog, Loading, Notice, PageHead } from "../ui/kit";
import { RoadmapView } from "./RoadmapScreen";
import { isMilestone, nextUp, progressOf } from "./roadmap/steps";
import { ReviewStep } from "./setup/ReviewStep";
import { UploadStep } from "./setup/UploadStep";

const stops: { stage: Stage; label: string }[] = [
  { stage: "upload", label: "Đưa đề cương vào" },
  { stage: "review", label: "Kiểm tra nội dung" },
  { stage: "plan", label: "Duyệt lộ trình" },
];
const heads: Record<Exclude<Stage, "ready">, [string, string]> = {
  upload: [
    "Bắt đầu từ đề cương",
    "Pathly đọc đề cương môn học, bạn kiểm tra lại, rồi nhận một lộ trình học theo từng tuần.",
  ],
  review: [
    "Kiểm tra đề cương",
    "Đây là những gì đọc được. Sửa chỗ sai trước khi tạo lộ trình: lộ trình chỉ đúng khi đề cương đúng.",
  ],
  plan: [
    "Lộ trình đề xuất",
    "Mỗi chủ đề là một bước, mỗi bài kiểm tra là một mốc. Chọn một bước để chỉnh thứ tự học, rồi duyệt.",
  ],
};

/** What the learner called the course, from the syllabus when it has a title. */
export function courseName(course: Course): string {
  const info = course.draft?.course;
  return String(info?.title?.value || info?.code?.value || course.draft?.file_name || "Môn học của bạn");
}

/** The setup as three stations on a line; earlier stations stay reachable. */
function Stops({ course }: { course: Course }) {
  const at = stops.findIndex((s) => s.stage === course.stage);
  return (
    <ol className="stops" aria-label="Các bước thiết lập">
      {stops.map((stop, i) => (
        <li key={stop.stage} className={i < at ? "stop-done" : ""} aria-current={i === at ? "step" : undefined}>
          {i < at ? (
            <button type="button" disabled={course.busy} onClick={() => course.setStage(stop.stage)}>
              {stop.label}
            </button>
          ) : (
            <span>{stop.label}</span>
          )}
        </li>
      ))}
    </ol>
  );
}

/** The home of the course once its roadmap is approved: where you are and what comes next. */
// FSRS ratings the server accepts (1-4), in the order a learner reads them.
const RATINGS = [
  { value: 1, label: "Quên" },
  { value: 2, label: "Khó" },
  { value: 3, label: "Được" },
  { value: 4, label: "Dễ" },
];

/** Spaced-repetition cards due now, one at a time; hidden when nothing is due. */
function DueReviews() {
  const [cards, setCards] = useState<DueReviewCard[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    fetchDueReviews(20).then(
      (due) => current && setCards(due),
      () => current && setCards([]),
    );
    return () => {
      current = false;
    };
  }, []);
  if (!cards?.length) return null;
  const card = cards[0];
  const rate = async (rating: number) => {
    setBusy(true);
    setError("");
    try {
      await submitReview(card.item_id, rating, card.node_id ?? undefined);
      setCards((all) => all?.slice(1) ?? []);
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="section" aria-labelledby="review-title">
      <div className="section-head">
        <h2 id="review-title">Ôn tập đến hạn</h2>
        <p className="muted">Còn {cards.length} thẻ</p>
      </div>
      <div className="review-card">
        <p className="review-prompt">{card.prompt}</p>
        {card.choices && card.choices.length > 0 && (
          <ol className="review-choices">
            {card.choices.map((choice) => (
              <li key={choice}>{choice}</li>
            ))}
          </ol>
        )}
        <p className="muted small" id="review-ask">
          Tự trả lời trong đầu, rồi chọn mức bạn nhớ được.
        </p>
        <div className="row" role="group" aria-labelledby="review-ask">
          {RATINGS.map((r) => (
            <Button key={r.value} size="sm" disabled={busy} onClick={() => void rate(r.value)}>
              {r.label}
            </Button>
          ))}
        </div>
        {error && <Notice tone="error">{error}</Notice>}
      </div>
    </section>
  );
}

function Overview({ course, go }: { course: Course; go: (route: Route) => void }) {
  const [resetting, setResetting] = useState(false);
  const steps = course.roadmap!.nodes;
  const progress = progressOf(steps);
  const { current, milestone } = nextUp(steps);
  const open = (id: string) => {
    course.setSelectedId(id);
    go("roadmap");
  };

  return (
    <>
      <PageHead
        title={courseName(course)}
        lead="Lộ trình đã duyệt. Học theo từng tuần, và xếp các bước vào lịch khi bạn sẵn sàng."
        actions={
          <>
            <a className="btn btn-secondary btn-md" href="#schedule">
              Xếp lịch học
            </a>
            <a className="btn btn-primary btn-md" href="#roadmap">
              Mở lộ trình
            </a>
          </>
        }
      />

      <section className="section" aria-labelledby="progress-title">
        <div className="section-head">
          <h2 id="progress-title">Tiến độ</h2>
          <p className="muted">
            {progress.done}/{progress.total} bước đã xong
          </p>
        </div>
        <div
          className="meter"
          role="progressbar"
          aria-labelledby="progress-title"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress.percent}
        >
          <span style={{ width: `${progress.percent}%` }} />
        </div>
      </section>

      <div className="overview">
        <section className="section" aria-labelledby="next-title">
          <h2 id="next-title">{current ? `Tiếp theo: tuần ${current.week}` : "Bạn đã học hết các bước"}</h2>
          {current ? (
            <ul className="next-list">
              {current.steps.map((step) => (
                <li key={step.id}>
                  <button type="button" onClick={() => open(step.id)}>
                    <span className={isMilestone(step) ? "mark mark-milestone" : "mark"} aria-hidden="true" />
                    <span className="grow">{step.title}</span>
                    {isMilestone(step) && <Chip tone="signal">Mốc kiểm tra</Chip>}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="muted">Ôn lại các mốc kiểm tra trong lộ trình khi cần.</p>
          )}
        </section>

        <section className="section" aria-labelledby="milestone-title">
          <h2 id="milestone-title">Mốc kiểm tra sắp tới</h2>
          {milestone ? (
            <button type="button" className="milestone-card" onClick={() => open(milestone.id)}>
              <span className="mark mark-milestone" aria-hidden="true" />
              <span className="grow">
                <strong>{milestone.title}</strong>
                <span className="muted small">
                  Tuần {milestone.week ?? 1}
                  {milestone.covers.length > 0 && `, kiểm tra ${milestone.covers.length} bước`}
                </span>
              </span>
            </button>
          ) : (
            <p className="muted">Đề cương không có bài kiểm tra nào từ tuần này trở đi.</p>
          )}
        </section>
      </div>

      {!course.mock && <DueReviews />}

      <section className="section">
        <div className="row">
          <Button variant="quiet" disabled={course.busy} onClick={() => void course.editSyllabus()}>
            Sửa đề cương
          </Button>
          <Button variant="quiet" onClick={() => setResetting(true)}>
            Bắt đầu lại với đề cương khác
          </Button>
        </div>
        {course.error && <Notice tone="error">{course.error}</Notice>}
      </section>

      {resetting && (
        <Dialog
          title="Bắt đầu lại?"
          onClose={() => setResetting(false)}
          footer={
            <>
              <Button onClick={() => setResetting(false)}>Giữ lộ trình này</Button>
              <Button variant="danger" onClick={course.startOver}>
                Bắt đầu lại
              </Button>
            </>
          }
        >
          <p>
            {course.mock
              ? "Đề cương và lộ trình của bản xem thử sẽ bị xóa khỏi trình duyệt này."
              : "Ứng dụng sẽ quay về bước đưa đề cương vào. Lộ trình đã lưu vẫn nằm trên máy chủ."}
          </p>
        </Dialog>
      )}
    </>
  );
}

/** The course screen: the three-step setup until a roadmap is approved, then the overview. */
export function CourseScreen({ course, go }: { course: Course; go: (route: Route) => void }) {
  if (course.restoring) return <Loading>Đang mở lộ trình của bạn…</Loading>;
  if (course.stage === "ready" && course.roadmap) return <Overview course={course} go={go} />;

  const stage = course.stage === "ready" ? "upload" : course.stage;
  const [title, lead] = heads[stage];
  return (
    <>
      <Stops course={course} />
      <PageHead title={title} lead={lead} />
      {stage === "upload" && (
        <>
          <UploadStep course={course} />
          {course.error && <Notice tone="error">{course.error}</Notice>}
        </>
      )}
      {stage === "review" && <ReviewStep course={course} />}
      {stage === "plan" && (
        <>
          <RoadmapView course={course} />
          {course.error && <Notice tone="error">{course.error}</Notice>}
          <div className="action-bar">
            <Button variant="quiet" disabled={course.busy} onClick={() => course.setStage("review")}>
              Sửa đề cương
            </Button>
            <div className="row row-end grow">
              <Button variant="primary" disabled={course.busy} onClick={() => void course.approve()}>
                {course.busy ? "Đang lưu…" : "Duyệt lộ trình"}
              </Button>
            </div>
          </div>
        </>
      )}
    </>
  );
}
