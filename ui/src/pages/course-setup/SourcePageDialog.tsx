import { useEffect, useState } from "react";
import { call } from "../../api/backend";
import { Button } from "../../components/Button";
import { Modal } from "../../components/Modal";

type SourcePage = { id: string; file_name: string; page: number; text: string };
export function SourcePageDialog({
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
  const [result, setResult] = useState<SourcePage | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setResult(null);
    setError("");
    call<SourcePage[]>(`/courses/${encodeURIComponent(courseId)}/sources`)
      .then((rows) => {
        const source = rows.find((r) => r.id === sourceId);
        const found =
          source &&
          rows.find((r) => r.file_name === source.file_name && r.page === page);
        if (active) {
          if (found) setResult(found);
          else setError("This source page could not be found.");
        }
      })
      .catch((e) => {
        if (active)
          setError(
            e instanceof Error ? e.message : "Could not load source page.",
          );
      });
    return () => {
      active = false;
    };
  }, [courseId, sourceId, page, retry]);
  return (
    <Modal
      title={
        result
          ? `${result.file_name} · p. ${page}`
          : `Source page · p. ${page}`
      }
      onClose={onClose}
    >
      <div className="core-source-page">
        {error ? (
          <div>
            <p role="alert">{error}</p>
            <Button onClick={() => setRetry((n) => n + 1)}>
              Retry source page
            </Button>
          </div>
        ) : result ? (
          <p style={{ whiteSpace: "pre-wrap" }}>
            {result.text || "No extracted text is available for this page yet."}
          </p>
        ) : (
          <p role="status">Loading source page…</p>
        )}
      </div>
    </Modal>
  );
}
