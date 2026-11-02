import { useEffect, useRef, useState, type DragEvent } from "react";
import { backendEnabled } from "../api/backend";
import {
  ApiError,
  generateItems,
  proposeConcepts,
  uploadSource,
  type Item,
  type UploadResult,
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
  type Graph,
} from "../concepts";

type Row = UploadResult & { error?: string };
const STATUS = { processing: "Processing…", processed: "Done", error: "Error" };

/** A concept's cited practice questions (UC-03), each with its slide page. */
function Questions({
  title,
  state,
  onAsk,
}: {
  title: string;
  state: { busy?: boolean; error?: string; items?: Item[] };
  onAsk: () => void;
}) {
  return (
    <div className="questions">
      <button className="secondary-action" disabled={state.busy} onClick={onAsk}>
        {state.busy ? "Writing questions…" : state.items ? "More questions" : "Generate questions"}
      </button>
      {state.error && (
        <p role="alert" className="row-error">
          {state.error}
        </p>
      )}
      {state.items && (
        <ol className="question-list" aria-label={`Questions for ${title}`}>
          {state.items.map((i) => (
            <li key={i.id}>
              <p>{i.prompt}</p>
              {i.type === "mcq" ? (
                <ul>
                  {i.choices.map((choice) => (
                    <li key={choice}>
                      {choice === i.answer ? <strong>{choice} (answer)</strong> : choice}
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="hint">
                  Answer: {i.answer}
                  <br />
                  Rubric: {i.rubric.join("; ")}
                </p>
              )}
              <span className="citation">
                {i.file_name} · p. {i.page}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

/** S3 Upload + S4 Concept editor (spec section 5); api/courses.ts picks the backend or the demo. */
export function CoursesPage({ course }: { course: string }) {
  const [files, setFiles] = useState<Row[]>([]);
  const [graph, setGraph] = useState<Graph | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [undo, setUndo] = useState<{ graph: Graph; title: string } | null>(null);
  const [edgeError, setEdgeError] = useState<{ id: string; text: string } | null>(null);
  const [dragging, setDragging] = useState(false);
  const [proposing, setProposing] = useState(false);
  const [proposeError, setProposeError] = useState("");
  const [questions, setQuestions] = useState<
    Record<string, { busy?: boolean; error?: string; items?: Item[] }>
  >({});
  const picker = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!undo) return;
    const t = setTimeout(() => setUndo(null), 5000);
    return () => clearTimeout(t);
  }, [undo]);

  const update = (name: string, row: Partial<Row>) =>
    setFiles((fs) => fs.map((f) => (f.file_name === name ? { ...f, ...row } : f)));

  const upload = async (list: FileList | null) => {
    let proposed = graph !== null;
    for (const file of Array.from(list ?? [])) {
      const rejected = checkFile(file);
      setFiles((fs) => [
        ...fs.filter((f) => f.file_name !== file.name),
        {
          file_name: file.name,
          pages: 0,
          status: rejected ? "error" : "processing",
          error: rejected ? ERRORS[rejected] : undefined,
        },
      ]);
      if (rejected) continue;
      try {
        const result = await uploadSource(course, file);
        update(file.name, { ...result, error: result.warning && ERRORS[result.warning] });
      } catch (err) {
        update(file.name, {
          status: "error",
          error:
            err instanceof ApiError
              ? ERRORS[err.code]
              : err instanceof Error
                ? err.message
                : ERRORS.invalid_pdf,
        });
        continue;
      }
      // The backend extracts each new file; the demo shows its fixed sample once.
      if (proposed && !backendEnabled) continue;
      proposed = true;
      setProposing(true);
      setProposeError("");
      try {
        setGraph(await proposeConcepts(course, file.name));
      } catch (err) {
        setProposeError(
          err instanceof ApiError
            ? ERRORS[err.code]
            : err instanceof Error
              ? err.message
              : ERRORS.concepts_unavailable,
        );
      } finally {
        setProposing(false);
      }
    }
  };

  const drop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void upload(e.dataTransfer.files);
  };

  const ask = async (id: string) => {
    setQuestions((q) => ({ ...q, [id]: { ...q[id], busy: true, error: undefined } }));
    try {
      const items = await generateItems(course, id);
      setQuestions((q) => ({ ...q, [id]: { items } }));
    } catch (err) {
      const error =
        err instanceof ApiError
          ? ERRORS[err.code]
          : err instanceof Error
            ? err.message
            : ERRORS.items_unavailable;
      setQuestions((q) => ({ ...q, [id]: { ...q[id], busy: false, error } }));
    }
  };

  const edit = (next: Graph) => {
    setGraph(next);
    setEdgeError(null);
  };
  const confirmed = graph?.concepts.filter((c) => c.confirmed).length ?? 0;
  const allConfirmed = !!graph && graph.concepts.length > 0 && confirmed === graph.concepts.length;
  const title = (id: string) => graph?.concepts.find((c) => c.id === id)?.title ?? id;

  return (
    <section className="courses" aria-labelledby="upload-title">
      <div className="card">
        <h2 id="upload-title">Course materials</h2>
        <p className="hint">
          {backendEnabled
            ? "AI reads your slides and proposes concepts; this can take a minute or two per file. Concept edits are not saved yet."
            : "Demo: files are checked locally. Concepts are fixed Week 1 examples, not extracted from your PDF. Edits last until you reload."}
        </p>
        <div
          className={`dropzone ${dragging ? "dragging" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          // Ignore leave events fired when the pointer moves onto a child of the zone.
          onDragLeave={(e) => {
            if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setDragging(false);
          }}
          onDrop={drop}
        >
          <p>Drag and drop PDF files here (up to 20 MB)</p>
          <button className="primary-action" onClick={() => picker.current?.click()}>
            Choose PDF files
          </button>
          <input
            ref={picker}
            type="file"
            accept="application/pdf,.pdf"
            multiple
            hidden
            aria-label="Choose PDF files to upload"
            onChange={(e) => {
              void upload(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
        {files.length > 0 && (
          <ul className="file-list" aria-live="polite">
            {files.map((f) => (
              <li key={f.file_name} className={f.status}>
                <span>{f.file_name}</span>
                <span>{f.pages ? `${f.pages} ${f.pages === 1 ? "page" : "pages"}` : ""}</span>
                <span>{STATUS[f.status]}</span>
                {f.error && <span className="row-error">{f.error}</span>}
              </li>
            ))}
          </ul>
        )}
      </div>

      {proposing && (
        <p className="card proposing" role="status">
          Finding concepts in your slides…
        </p>
      )}
      {proposeError && (
        <p className="card row-error" role="alert">
          {proposeError}
        </p>
      )}

      {graph && (
        <div className="card">
          <div className="concept-toolbar">
            <h2>
              Concepts ({graph.concepts.length})
              <span className="confirm-count">
                {confirmed} of {graph.concepts.length} confirmed
              </span>
            </h2>
            <button
              className="secondary-action"
              disabled={selected.length !== 2}
              onClick={() => {
                edit(merge(graph, selected[0], selected[1]));
                setSelected([]);
              }}
            >
              Merge ({selected.length}/2)
            </button>
            <button
              className="primary-action"
              disabled={allConfirmed}
              onClick={() => edit(confirmAll(graph))}
            >
              {allConfirmed ? "All confirmed ✓" : "Confirm all"}
            </button>
          </div>
          <p className="hint">Tick two concepts to merge them. Edit a name to rename it.</p>
          {graph.concepts.length === 0 && <p>No concepts yet.</p>}
          <ul className="concept-list">
            {graph.concepts.map((c) => {
              const parents = graph.prereqs.filter((p) => p.child_id === c.id);
              return (
                <li key={c.id} className={c.confirmed ? "confirmed" : ""}>
                  <input
                    type="checkbox"
                    aria-label={`Select ${c.title} to merge`}
                    checked={selected.includes(c.id)}
                    onChange={(e) =>
                      setSelected((s) =>
                        e.target.checked ? [...s, c.id].slice(-2) : s.filter((x) => x !== c.id),
                      )
                    }
                  />
                  <div className="concept-body">
                    <input
                      className="concept-title"
                      aria-label={`Rename ${c.title}`}
                      value={c.title}
                      onChange={(e) => edit(rename(graph, c.id, e.target.value))}
                    />
                    <p>{c.summary}</p>
                    <span className="citation">
                      {c.source_file && `${c.source_file} · `}p. {c.source_pages.join(", ")}
                    </span>
                    {parents.length > 0 && (
                      <div className="parents">
                        Learn first:
                        {parents.map((p) => (
                          <span key={p.parent_id} className="prereq-chip">
                            {title(p.parent_id)}
                            <button
                              aria-label={`Remove prerequisite ${title(p.parent_id)} from ${c.title}`}
                              onClick={() => edit(removePrereq(graph, p.parent_id, c.id))}
                            >
                              ×
                            </button>
                          </span>
                        ))}
                      </div>
                    )}
                    <select
                      aria-label={`Add a prerequisite for ${c.title}`}
                      value=""
                      onChange={(e) => {
                        const result = addPrereq(graph, e.target.value, c.id);
                        if ("error" in result) setEdgeError({ id: c.id, text: result.error });
                        else edit(result);
                      }}
                    >
                      <option value="">+ Add prerequisite…</option>
                      {graph.concepts
                        .filter((o) => o.id !== c.id)
                        .map((o) => (
                          <option key={o.id} value={o.id}>
                            {o.title}
                          </option>
                        ))}
                    </select>
                    {edgeError?.id === c.id && (
                      <p role="alert" className="row-error">
                        {edgeError.text}
                      </p>
                    )}
                    {/* Demo concepts are not stored, so only the backend can write questions. */}
                    {backendEnabled && (
                      <Questions
                        title={c.title}
                        state={questions[c.id] ?? {}}
                        onAsk={() => void ask(c.id)}
                      />
                    )}
                  </div>
                  <button
                    className="secondary-action"
                    aria-label={`Delete ${c.title}`}
                    onClick={() => {
                      setUndo({ graph, title: c.title });
                      edit(remove(graph, c.id));
                      setSelected((s) => s.filter((x) => x !== c.id));
                    }}
                  >
                    Delete
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {undo && (
        <div className="toast" role="status">
          Deleted “{undo.title}”.{" "}
          <button
            className="undo"
            onClick={() => {
              edit(undo.graph);
              setUndo(null);
            }}
          >
            Undo
          </button>
        </div>
      )}
    </section>
  );
}
