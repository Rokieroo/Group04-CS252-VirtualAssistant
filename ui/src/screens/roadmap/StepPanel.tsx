import { useCallback, useEffect, useRef, useState } from "react";
import { call } from "../../api/backend";
import { fetchNodeExercises, type ExerciseItem } from "../../api/exercises";
import {
  decideMaterial,
  nodeMaterials,
  nodeSources,
  pageRanges,
  type MaterialFile,
  type NodeSources,
} from "../../api/materials";
import { fetchNodeResources, searchNodeResources, sendResourceFeedback } from "../../api/resources";
import type { NodeResources, Resource } from "../../api/types";
import { duration, explain, statusLabels } from "../../app/text";
import type { Course } from "../../app/useCourse";
import { Icon } from "../../ui/icons";
import { Button, Chip, Dialog, IconButton, Loading, Notice } from "../../ui/kit";
import { SourceCard } from "./SourceCard";
import { isMilestone, minutesOf, statusOf, type Step } from "./steps";

const POLL_MS = 3000;

/** One page of an uploaded file, as text. The server lists a course's pages; pick the one asked for. */
function MaterialPage({
  courseId,
  sourceId,
  page,
  onClose,
}: {
  courseId: string;
  sourceId: string;
  page: number;
  onClose: () => void;
}) {
  type Row = { id: string; file_name: string; page: number; text: string };
  const [row, setRow] = useState<Row | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    call<Row[]>(`/courses/${encodeURIComponent(courseId)}/sources`).then(
      (rows) => {
        const file = rows.find((r) => r.id === sourceId)?.file_name;
        const found = rows.find((r) => r.file_name === file && r.page === page);
        if (!current) return;
        if (found) setRow(found);
        else setError("Không tìm thấy trang tài liệu này.");
      },
      (reason) => current && setError(explain(reason)),
    );
    return () => {
      current = false;
    };
  }, [courseId, sourceId, page]);
  return (
    <Dialog
      wide
      title={row ? `${row.file_name}, trang ${page}` : `Trang ${page}`}
      onClose={onClose}
      footer={<Button onClick={onClose}>Đóng</Button>}
    >
      {error ? (
        <Notice tone="error">{error}</Notice>
      ) : row ? (
        <p className="pre">{row.text || "Trang này chưa có văn bản trích xuất."}</p>
      ) : (
        <Loading>Đang tải trang tài liệu…</Loading>
      )}
    </Dialog>
  );
}

/**
 * Where to learn this step, most trusted first: the learner's own pages, then sources the
 * catalog verified, then web results (which can be rated and searched again).
 */
function Sources({ nodeId, courseId }: { nodeId: string; courseId?: string }) {
  const [own, setOwn] = useState<NodeSources | null>(null);
  const [files, setFiles] = useState<MaterialFile[]>([]);
  const [web, setWeb] = useState<NodeResources | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [rated, setRated] = useState<Record<string, boolean>>({});
  const [page, setPage] = useState<{ sourceId: string; page: number } | null>(null);
  const version = useRef(0);

  const load = useCallback(async () => {
    const mine = ++version.current;
    const [a, b, c] = await Promise.allSettled([
      nodeSources(nodeId),
      nodeMaterials(nodeId),
      fetchNodeResources(nodeId),
    ]);
    if (mine !== version.current) return;
    if (a.status === "fulfilled") setOwn(a.value);
    if (b.status === "fulfilled") setFiles(b.value);
    if (c.status === "fulfilled") setWeb(c.value);
    const failed = [a, b, c].find((r) => r.status === "rejected") as PromiseRejectedResult | undefined;
    setError(failed ? explain(failed.reason) : "");
    setLoaded(true);
  }, [nodeId]);

  useEffect(() => {
    void load();
    return () => {
      ++version.current;
    };
  }, [load]);

  // A web search runs as a background job; the server answers "searching" until it ends.
  useEffect(() => {
    if (web?.status !== "searching") return;
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [web?.status, load]);

  const act = async (work: () => Promise<unknown>) => {
    setBusy(true);
    try {
      await work();
      await load();
    } catch (e) {
      setError(explain(e));
    } finally {
      setBusy(false);
    }
  };
  const rate = (resource: Resource, helpful: boolean) =>
    act(async () => {
      await sendResourceFeedback(resource.id, { node_id: nodeId, helpful });
      setRated((current) => ({ ...current, [resource.id]: helpful }));
    });

  if (!loaded) return <Loading>Đang tải nguồn học…</Loading>;

  const mine = own?.sources.filter((s) => s.kind === "user_material") ?? [];
  const catalog = own?.sources.filter((s) => s.kind === "catalog") ?? [];
  // Outside sources the server matched (not from the catalog): shown with the web results, never verified.
  const external = own?.sources.filter((s) => s.kind === "external" || s.kind === "web") ?? [];
  const suggested = files.filter((f) => f.status === "suggested");
  const pageButton = (sourceId: string, number: number) => (
    <button
      key={`${sourceId}:${number}`}
      type="button"
      className="cite"
      disabled={!courseId}
      onClick={() => setPage({ sourceId, page: number })}
    >
      tr. {number}
    </button>
  );

  return (
    <div className="stack">
      {error && (
        <Notice
          tone="error"
          action={
            <Button size="sm" disabled={busy} onClick={() => void act(async () => {})}>
              Thử lại
            </Button>
          }
        >
          {error}
        </Notice>
      )}

      <section className="source-group" aria-label="Tài liệu của bạn">
        <h4>Tài liệu của bạn</h4>
        {mine.length === 0 && suggested.length === 0 && (
          <p className="muted small">
            Chưa có trang nào khớp với bước này. Tải bài giảng lên ở mục <a href="#library">Tài liệu</a>.
          </p>
        )}
        {mine.map((s) => (
          <div className="own-source" key={s.id}>
            <strong>{s.title}</strong>
            {s.reason && <p className="muted small">{s.reason}</p>}
            <div className="row">{s.pages.map((p) => pageButton(s.source_id || s.id, p))}</div>
          </div>
        ))}
        {suggested.map((file) => (
          <div className="own-source own-suggested" key={file.file_name}>
            <p>
              <strong>{file.file_name}</strong>, trang {pageRanges(file.pages.map((p) => p.page))}, có
              thuộc bước này không?
            </p>
            <div className="row">
              <Button
                size="sm"
                variant="primary"
                disabled={busy}
                onClick={() => void act(() => decideMaterial(nodeId, file, true))}
              >
                Đúng, gắn vào bước này
              </Button>
              <Button
                size="sm"
                disabled={busy}
                onClick={() => void act(() => decideMaterial(nodeId, file, false))}
              >
                Không phải
              </Button>
            </div>
          </div>
        ))}
      </section>

      <section className="source-group" aria-label="Nguồn đã kiểm chứng">
        <h4>Nguồn đã kiểm chứng</h4>
        {catalog.length === 0 && (
          <p className="muted small">Kho nguồn chưa có tài liệu đã kiểm chứng cho bước này.</p>
        )}
        {catalog.map((s) => (
          <SourceCard
            key={s.id}
            title={s.title}
            url={s.url}
            from={s.institution || s.provider}
            format={s.format}
            minutes={s.duration_min}
            license={s.license}
            reason={s.reason}
            verified={s.verification_status === "verified"}
          />
        ))}
      </section>

      <section className="source-group" aria-label="Nguồn trên web">
        <div className="section-head">
          <h4>Trên web</h4>
          <Button
            size="sm"
            variant="quiet"
            icon="refresh"
            disabled={busy || web?.status === "searching"}
            onClick={() => void act(() => searchNodeResources(nodeId))}
          >
            Tìm lại
          </Button>
        </div>
        {web?.status === "searching" && <Loading>Đang tìm nguồn học trên web…</Loading>}
        {web?.status === "insufficient" && (
          <p className="muted small">
            Chưa tìm đủ nguồn đạt chất lượng.{web.gaps.length > 0 && ` Còn thiếu: ${web.gaps.join("; ")}.`}
          </p>
        )}
        {web?.status === "ready" && web.resources.length === 0 && external.length === 0 && (
          <p className="muted small">Chưa có nguồn nào trên web cho bước này.</p>
        )}
        {external.map((s) => (
          <SourceCard
            key={s.id}
            title={s.title}
            url={s.url}
            from={s.institution || s.provider}
            format={s.format}
            minutes={s.duration_min}
            license={s.license}
            reason={s.reason}
          />
        ))}
        {web?.resources.map((r) => (
          <SourceCard
            key={r.id}
            title={r.title}
            url={r.url}
            from={r.domain}
            format={r.format}
            minutes={r.duration_min}
            reason={r.reason}
          >
            {r.id in rated ? (
              <span className="muted small" role="status">
                Đã ghi nhận đánh giá của bạn.
              </span>
            ) : (
              <>
                <Button size="sm" disabled={busy} onClick={() => void rate(r, true)}>
                  Hữu ích
                </Button>
                <Button size="sm" variant="quiet" disabled={busy} onClick={() => void rate(r, false)}>
                  Không phù hợp
                </Button>
              </>
            )}
          </SourceCard>
        ))}
      </section>

      {page && courseId && (
        <MaterialPage courseId={courseId} {...page} onClose={() => setPage(null)} />
      )}
    </div>
  );
}

/** A taste of the cited practice questions for this step; each names the page it came from. */
function Exercises({ nodeId }: { nodeId: string }) {
  const [items, setItems] = useState<ExerciseItem[] | null>(null);
  useEffect(() => {
    let current = true;
    fetchNodeExercises(nodeId, 3).then(
      (result) => current && setItems(result.exercises),
      () => current && setItems([]),
    );
    return () => {
      current = false;
    };
  }, [nodeId]);
  if (!items?.length) return null;
  return (
    <section className="panel-section">
      <h3>Bài luyện tập</h3>
      <ol className="exercises">
        {items.map((item) => (
          <li key={item.id}>
            <p>{item.prompt}</p>
            <span className="muted small">
              Nguồn: {item.citation.institution || item.citation.title}
              {item.citation.page ? `, trang ${item.citation.page}` : ""}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

/**
 * Everything about one step, docked beside the roadmap (a sheet on phones): what it is,
 * what must come first, and where to learn it. It is not modal: the roadmap stays usable.
 */
export function StepPanel({ course, step, onClose }: { course: Course; step: Step; onClose: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null);
  const [edgeError, setEdgeError] = useState("");
  const roadmap = course.roadmap!;
  const find = (id: string) => roadmap.nodes.find((n) => n.id === id);

  useEffect(() => {
    heading.current?.focus({ preventScroll: true });
    setEdgeError("");
  }, [step.id]);
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      // An open dialog (a source page) owns Esc first.
      if (event.key === "Escape" && !document.querySelector('[aria-modal="true"]')) onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  const before = roadmap.edges.filter((e) => e.child_id === step.id);
  const after = roadmap.edges.filter((e) => e.parent_id === step.id);
  const candidates = roadmap.nodes.filter(
    (n) => n.id !== step.id && !isMilestone(n) && !before.some((e) => e.parent_id === n.id),
  );
  const covered = step.covers.map(find).filter((n): n is Step => Boolean(n));
  const status = statusOf(step);
  const jump = (id: string) => (
    <button key={id} type="button" className="link-chip" onClick={() => course.setSelectedId(id)}>
      {find(id)?.title ?? id}
    </button>
  );

  return (
    <section className="step-panel" aria-label={`Chi tiết: ${step.title}`}>
      <header className="step-head">
        <div className="grow">
          <div className="row">
            <Chip tone={isMilestone(step) ? "signal" : "plain"}>
              {isMilestone(step) ? "Mốc kiểm tra" : "Bước học"}
            </Chip>
            <Chip>Tuần {step.week ?? 1}</Chip>
            {!isMilestone(step) && minutesOf(step) > 0 && (
              <Chip>
                <Icon name="clock" size={12} />
                {duration(minutesOf(step))}
              </Chip>
            )}
            {status !== "available" && <Chip tone="route">{statusLabels[status]}</Chip>}
          </div>
          <h2 ref={heading} tabIndex={-1}>
            {step.title}
          </h2>
        </div>
        <IconButton icon="close" label="Đóng chi tiết" onClick={onClose} />
      </header>

      <div className="step-body">
        {covered.length > 0 && (
          <section className="panel-section">
            <h3>Kiểm tra {covered.length} bước</h3>
            <div className="row">{covered.map((n) => jump(n.id))}</div>
          </section>
        )}

        <section className="panel-section">
          <h3>Cần học trước</h3>
          {before.length === 0 && <p className="muted small">Không cần học gì trước bước này.</p>}
          <ul className="prereqs">
            {before.map((edge) => (
              <li key={edge.parent_id}>
                {jump(edge.parent_id)}
                {edge.kind === "soft" && <span className="muted small">theo thứ tự tuần</span>}
                <IconButton
                  icon="close"
                  label={`Bỏ "${find(edge.parent_id)?.title}" khỏi phần cần học trước`}
                  onClick={async () => setEdgeError((await course.removeEdge(edge)) ?? "")}
                />
              </li>
            ))}
          </ul>
          {candidates.length > 0 && (
            <select
              aria-label="Thêm bước cần học trước"
              value=""
              onChange={async (event) => setEdgeError((await course.addEdge(event.target.value, step.id)) ?? "")}
            >
              <option value="">Thêm bước cần học trước…</option>
              {candidates.map((n) => (
                <option key={n.id} value={n.id}>
                  Tuần {n.week ?? 1}: {n.title}
                </option>
              ))}
            </select>
          )}
          {edgeError && (
            <p className="field-error" role="alert">
              {edgeError}
            </p>
          )}
        </section>

        {after.length > 0 && (
          <section className="panel-section">
            <h3>Học xong sẽ mở ra</h3>
            <div className="row">{after.map((edge) => jump(edge.child_id))}</div>
          </section>
        )}

        <section className="panel-section">
          <h3>Nguồn học</h3>
          {course.mock ? (
            <p className="muted small">
              Bản xem thử không tìm nguồn học. Ứng dụng đầy đủ xếp tài liệu của bạn lên đầu, rồi đến
              nguồn đã kiểm chứng và nguồn trên web.
            </p>
          ) : (
            <Sources key={step.id} nodeId={step.id} courseId={roadmap.course_id} />
          )}
        </section>

        {!course.mock && <Exercises key={step.id} nodeId={step.id} />}
      </div>
    </section>
  );
}
