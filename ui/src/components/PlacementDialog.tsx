import { useEffect, useState, type FormEvent } from "react";
import {
  answerPlacement,
  startPlacement,
  type PlacementState,
} from "../api/placement";
import { Modal } from "./Modal";

/** Placement test (UC-17, #166): quoted, cited questions; the result marks the graph. */
export function PlacementDialog({
  roadmapId,
  onClose,
  onFinished,
}: {
  roadmapId: string;
  onClose: () => void;
  onFinished: () => void;
}) {
  const [state, setState] = useState<PlacementState | null>(null);
  const [response, setResponse] = useState("");
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");

  // The finished result is saved on the graph's nodes: tell the caller to reload.
  function show(next: PlacementState) {
    setState(next);
    if (next.status === "finished") onFinished();
  }

  useEffect(() => {
    let cancelled = false;
    startPlacement(roadmapId)
      .then((s) => !cancelled && show(s))
      .catch((e) => !cancelled && setError(e instanceof Error ? e.message : String(e)))
      .finally(() => !cancelled && setBusy(false));
    return () => {
      cancelled = true;
    };
  }, [roadmapId]); // start once per roadmap, not on every new onFinished

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!state?.question || !response.trim()) return;
    setBusy(true);
    setError("");
    try {
      show(await answerPlacement(state.id, state.question.exercise.id, response));
      setResponse("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const last = state?.last_attempt;
  const question = state?.status === "active" ? state.question : null;
  return (
    <Modal title="Kiểm tra xếp lớp" onClose={onClose}>
      {error && <p role="alert">{error}</p>}
      {last && (
        <p role="status">
          {last.correct ? "Đúng." : "Chưa đúng."} Đáp án của nguồn:{" "}
          {last.source_answer ?? "—"}
        </p>
      )}
      {state && question && (
        <form onSubmit={submit}>
          <p className="sm">
            Câu {state.asked + 1} / tối đa {state.max_questions} · {question.title}
          </p>
          <p>{question.exercise.prompt}</p>
          {question.exercise.choices.length > 0 ? (
            <fieldset>
              <legend className="sm">Chọn một đáp án</legend>
              {question.exercise.choices.map((choice) => (
                <label key={choice}>
                  <input
                    type="radio"
                    name="placement-choice"
                    value={choice}
                    checked={response === choice}
                    onChange={() => setResponse(choice)}
                  />{" "}
                  {choice}
                </label>
              ))}
            </fieldset>
          ) : (
            <label>
              Câu trả lời
              <input
                value={response}
                maxLength={4000}
                onChange={(e) => setResponse(e.target.value)}
              />
            </label>
          )}
          <p className="np-citation-chip">
            📖 {question.exercise.location} ·{" "}
            {question.exercise.citation.institution ||
              question.exercise.citation.title}
            {question.exercise.citation.page
              ? ` · Trang ${question.exercise.citation.page}`
              : ""}
          </p>
          <button
            className="button"
            type="submit"
            disabled={busy || !response.trim()}
          >
            Trả lời
          </button>
        </form>
      )}
      {state?.status === "finished" && (
        <div role="status">
          <p>
            Bạn đã biết {state.known.length} chặng: lộ trình bớt{" "}
            {state.known_minutes} / {state.total_minutes} phút.
          </p>
          {state.skipped.length > 0 && (
            <p className="sm">
              {state.skipped.length} chặng chưa có bài tập để kiểm tra nên giữ
              nguyên.
            </p>
          )}
          <p className="sm">
            Các chặng đã biết được tô trên graph; mở một chặng để sửa nếu chưa
            đúng.
          </p>
          <button className="button" type="button" onClick={onClose}>
            Xem graph
          </button>
        </div>
      )}
      {busy && !state && <p role="status">Đang chuẩn bị câu hỏi…</p>}
    </Modal>
  );
}
