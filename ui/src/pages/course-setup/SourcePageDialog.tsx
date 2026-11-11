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
          else setError("Không tìm thấy trang tài liệu này.");
        }
      })
      .catch((e) => {
        if (active)
          setError(
            e instanceof Error ? e.message : "Không tải được trang tài liệu.",
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
          ? `${result.file_name} · tr. ${page}`
          : `Trang tài liệu · tr. ${page}`
      }
      onClose={onClose}
    >
      <div className="core-source-page">
        {error ? (
          <div>
            <p role="alert">{error}</p>
            <Button onClick={() => setRetry((n) => n + 1)}>
              Thử lại trang tài liệu
            </Button>
          </div>
        ) : result ? (
          <p style={{ whiteSpace: "pre-wrap" }}>
            {result.text || "Trang này chưa có văn bản trích xuất."}
          </p>
        ) : (
          <p role="status">Đang tải trang tài liệu…</p>
        )}
      </div>
    </Modal>
  );
}
