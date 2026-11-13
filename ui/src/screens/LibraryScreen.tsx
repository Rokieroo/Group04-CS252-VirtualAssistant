import { useEffect, useRef, useState, type DragEvent } from "react";
import { call } from "../api/backend";
import {
  ApiError,
  courseId,
  currentCourse,
  deleteSource,
  generateItems,
  proposeConcepts,
  uploadSource,
  type Item,
} from "../api/courses";
import {
  addPrereq,
  checkFile,
  confirmAll,
  ERRORS,
  merge,
  remove,
  removePrereq,
  rename,
  UPLOAD_ACCEPT,
  type Graph,
} from "../concepts";
import { explain } from "../app/text";
import { Icon } from "../ui/icons";
import { Button, Chip, Empty, IconButton, Loading, Notice, PageHead } from "../ui/kit";

type FileRow = { file_name: string; pages: number; status: "processing" | "processed" | "error"; note?: string };
type Asked = { busy?: boolean; error?: string; items?: Item[] };

const course = currentCourse.name;
/** Known upload codes read from ERRORS; anything else gets the general sentence. */
const reason = (error: unknown) => (error instanceof ApiError ? ERRORS[error.code] : explain(error));

/** Cited practice questions for one concept, written from the learner's own pages. */
function Questions({ title, state, onAsk }: { title: string; state: Asked; onAsk: () => void }) {
  return (
    <div className="stack">
      <div>
        <Button size="sm" disabled={state.busy} onClick={onAsk}>
          {state.busy ? "Đang viết câu hỏi…" : state.items ? "Viết thêm câu hỏi" : "Viết câu hỏi từ bài giảng"}
        </Button>
      </div>
      {state.error && (
        <p className="field-error" role="alert">
          {state.error}
        </p>
      )}
      {state.items && (
        <ol className="exercises" aria-label={`Câu hỏi cho ${title}`}>
          {state.items.map((item) => (
            <li key={item.id}>
              <p>{item.prompt}</p>
              {item.type === "mcq" ? (
                <ul className="choices">
                  {item.choices.map((choice) => (
                    <li key={choice}>{choice === item.answer ? <strong>{choice} (đáp án)</strong> : choice}</li>
                  ))}
                </ul>
              ) : (
                <p className="small">
                  Đáp án: {item.answer}
                  {item.rubric.length > 0 && `. Tiêu chí: ${item.rubric.join("; ")}`}
                </p>
              )}
              <span className="muted small">
                Nguồn: {item.file_name}, trang {item.page}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** The lecture files of the course and the concepts the AI finds in them. */
function Materials() {
  const picker = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<FileRow[] | null>(null);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [undo, setUndo] = useState<{ graph: Graph; title: string } | null>(null);
  const [edgeError, setEdgeError] = useState<{ id: string; text: string } | null>(null);
  const [over, setOver] = useState(false);
  const [proposing, setProposing] = useState(false);
  const [error, setError] = useState("");
  const [asked, setAsked] = useState<Record<string, Asked>>({});

  // Files uploaded on earlier visits: the server lists pages, so count them per file.
  useEffect(() => {
    let current = true;
    courseId(course)
      .then((id) => call<{ file_name: string }[]>(`/courses/${id}/sources`))
      .then(
        (rows) => {
          if (!current) return;
          const pages = new Map<string, number>();
          for (const row of rows) pages.set(row.file_name, (pages.get(row.file_name) ?? 0) + 1);
          setFiles((mine) => [
            ...[...pages].map(([file_name, count]) => ({ file_name, pages: count, status: "processed" as const })),
            ...(mine ?? []),
          ]);
        },
        (e) => {
          if (!current) return;
          setError(explain(e));
          setFiles((mine) => mine ?? []);
        },
      );
    return () => {
      current = false;
    };
  }, []);
  useEffect(() => {
    if (!undo) return;
    const timer = setTimeout(() => setUndo(null), 6000);
    return () => clearTimeout(timer);
  }, [undo]);

  const patch = (name: string, row: Partial<FileRow>) =>
    setFiles((list) => (list ?? []).map((f) => (f.file_name === name ? { ...f, ...row } : f)));

  const upload = async (list: FileList | null) => {
    for (const file of Array.from(list ?? [])) {
      const rejected = checkFile(file);
      setFiles((rows) => [
        ...(rows ?? []).filter((f) => f.file_name !== file.name),
        {
          file_name: file.name,
          pages: 0,
          status: rejected ? "error" : "processing",
          note: rejected ? ERRORS[rejected] : undefined,
        },
      ]);
      if (rejected) continue;
      try {
        const result = await uploadSource(course, file);
        patch(file.name, { ...result, note: result.warning && ERRORS[result.warning] });
      } catch (e) {
        patch(file.name, { status: "error", note: reason(e) });
        continue;
      }
      setProposing(true);
      setError("");
      try {
        setGraph(await proposeConcepts(course, file.name));
      } catch (e) {
        setError(reason(e));
      } finally {
        setProposing(false);
      }
    }
  };
  const drop = (event: DragEvent) => {
    event.preventDefault();
    setOver(false);
    void upload(event.dataTransfer.files);
  };
  const removeFile = async (name: string) => {
    try {
      await deleteSource(course, name);
      setFiles((list) => (list ?? []).filter((f) => f.file_name !== name));
    } catch (e) {
      patch(name, { note: reason(e) });
    }
  };
  const ask = async (id: string) => {
    setAsked((all) => ({ ...all, [id]: { ...all[id], busy: true, error: undefined } }));
    try {
      const items = await generateItems(course, id);
      setAsked((all) => ({ ...all, [id]: { items } }));
    } catch (e) {
      setAsked((all) => ({ ...all, [id]: { ...all[id], busy: false, error: reason(e) } }));
    }
  };
  const edit = (next: Graph) => {
    setGraph(next);
    setEdgeError(null);
  };

  const confirmed = graph?.concepts.filter((c) => c.confirmed).length ?? 0;
  const titleOf = (id: string) => graph?.concepts.find((c) => c.id === id)?.title ?? id;

  return (
    <>
      <section className="section" aria-labelledby="files-title">
        <h2 id="files-title">Bài giảng và tài liệu</h2>
        <div
          className={`drop ${over ? "drop-over" : ""}`}
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
            multiple
            accept={UPLOAD_ACCEPT}
            aria-label="Tệp bài giảng"
            onChange={(event) => {
              void upload(event.target.files);
              event.target.value = "";
            }}
          />
          <span className="drop-icon">
            <Icon name="upload" size={24} />
          </span>
          <strong>Kéo slide, PDF, Word hoặc ảnh chụp vào đây</strong>
          <span className="muted small">Mỗi tệp tối đa 20 MB. AI đọc từng trang, mỗi tệp mất một đến hai phút.</span>
          <Button onClick={() => picker.current?.click()}>Chọn tệp</Button>
        </div>

        {files === null ? (
          <Loading>Đang tải danh sách tệp…</Loading>
        ) : (
          files.length > 0 && (
            <ul className="plain-list" aria-live="polite">
              {files.map((f) => (
                <li key={f.file_name}>
                  <Icon name="file" size={18} />
                  <span className="grow">
                    <strong>{f.file_name}</strong>
                    {f.note && <span className={f.status === "error" ? "field-error" : "muted small"}> {f.note}</span>}
                  </span>
                  {f.pages > 0 && <span className="muted small">{f.pages} trang</span>}
                  {f.status === "processing" && <Chip tone="signal">Đang đọc…</Chip>}
                  {f.status === "error" && <Chip tone="danger">Lỗi</Chip>}
                  {f.status === "processed" && (
                    <IconButton icon="trash" label={`Xóa ${f.file_name}`} onClick={() => void removeFile(f.file_name)} />
                  )}
                </li>
              ))}
            </ul>
          )
        )}
        {proposing && <Loading>Đang tìm các khái niệm trong bài giảng…</Loading>}
        {error && <Notice tone="error">{error}</Notice>}
      </section>

      {graph && (
        <section className="section" aria-labelledby="concepts-title">
          <div className="section-head">
            <h2 id="concepts-title">Khái niệm ({graph.concepts.length})</h2>
            <div className="row">
              <span className="muted small">
                {confirmed}/{graph.concepts.length} đã xác nhận
              </span>
              <Button
                size="sm"
                disabled={picked.length !== 2}
                onClick={() => {
                  edit(merge(graph, picked[0], picked[1]));
                  setPicked([]);
                }}
              >
                Gộp ({picked.length}/2)
              </Button>
              <Button
                size="sm"
                variant="primary"
                disabled={graph.concepts.length === 0 || confirmed === graph.concepts.length}
                onClick={() => edit(confirmAll(graph))}
              >
                Xác nhận tất cả
              </Button>
            </div>
          </div>
          <p className="muted small">
            Đánh dấu hai khái niệm để gộp chúng. Sửa tên ngay trong ô. Các chỉnh sửa ở đây chưa được lưu lên máy
            chủ.
          </p>
          <ul className="concepts">
            {graph.concepts.map((c) => {
              const parents = graph.prereqs.filter((p) => p.child_id === c.id);
              return (
                <li key={c.id} className={c.confirmed ? "concept-confirmed" : ""}>
                  <input
                    type="checkbox"
                    aria-label={`Chọn ${c.title} để gộp`}
                    checked={picked.includes(c.id)}
                    onChange={(event) =>
                      setPicked((ids) =>
                        event.target.checked ? [...ids, c.id].slice(-2) : ids.filter((id) => id !== c.id),
                      )
                    }
                  />
                  <div className="stack grow">
                    <input
                      aria-label={`Tên khái niệm ${c.title}`}
                      value={c.title}
                      onChange={(event) => edit(rename(graph, c.id, event.target.value))}
                    />
                    <p>{c.summary}</p>
                    <span className="muted small">
                      {c.source_file && `${c.source_file}, `}trang {c.source_pages.join(", ")}
                    </span>
                    <div className="row">
                      {parents.length > 0 && <span className="small">Học trước:</span>}
                      {parents.map((p) => (
                        <span key={p.parent_id} className="chip">
                          {titleOf(p.parent_id)}
                          <button
                            type="button"
                            className="chip-x"
                            aria-label={`Bỏ ${titleOf(p.parent_id)} khỏi phần học trước của ${c.title}`}
                            onClick={() => edit(removePrereq(graph, p.parent_id, c.id))}
                          >
                            <Icon name="close" size={12} />
                          </button>
                        </span>
                      ))}
                    </div>
                    <select
                      aria-label={`Thêm khái niệm cần học trước ${c.title}`}
                      value=""
                      onChange={(event) => {
                        const result = addPrereq(graph, event.target.value, c.id);
                        if ("error" in result) setEdgeError({ id: c.id, text: result.error });
                        else edit(result);
                      }}
                    >
                      <option value="">Thêm khái niệm cần học trước…</option>
                      {graph.concepts
                        .filter((other) => other.id !== c.id)
                        .map((other) => (
                          <option key={other.id} value={other.id}>
                            {other.title}
                          </option>
                        ))}
                    </select>
                    {edgeError?.id === c.id && (
                      <p className="field-error" role="alert">
                        {edgeError.text}
                      </p>
                    )}
                    <Questions title={c.title} state={asked[c.id] ?? {}} onAsk={() => void ask(c.id)} />
                  </div>
                  <IconButton
                    icon="trash"
                    label={`Xóa khái niệm ${c.title}`}
                    onClick={() => {
                      setUndo({ graph, title: c.title });
                      edit(remove(graph, c.id));
                      setPicked((ids) => ids.filter((id) => id !== c.id));
                    }}
                  />
                </li>
              );
            })}
          </ul>
        </section>
      )}

      {undo && (
        <div className="toast" role="status">
          Đã xóa “{undo.title}”.
          <Button
            size="sm"
            onClick={() => {
              edit(undo.graph);
              setUndo(null);
            }}
          >
            Hoàn tác
          </Button>
        </div>
      )}
    </>
  );
}

export function LibraryScreen({ mock }: { mock: boolean }) {
  return (
    <>
      <PageHead
        title="Tài liệu"
        lead="Bài giảng của bạn là nguồn học đầu tiên: mỗi trang được gắn vào đúng bước của lộ trình."
      />
      {mock ? (
        <Empty icon="library" title="Tài liệu cần ứng dụng đầy đủ">
          Bản xem thử chạy hoàn toàn trong trình duyệt nên không lưu tệp. Ở ứng dụng đầy đủ, bạn tải slide và
          ghi chú lên, AI tìm các khái niệm và viết câu hỏi luyện tập có trích dẫn trang.
        </Empty>
      ) : (
        <Materials />
      )}
    </>
  );
}
