import { useEffect, useState } from "react";
import { call } from "../api/backend";
type Preferences = { guide_enabled: boolean; weekly_reminder: boolean };

export function LearningGuide({ step }: { step: number }) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [error, setError] = useState(""),
    [revision, retry] = useState(0),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    setError("");
    call<Preferences>("/me/learning-preferences")
      .then((p) => {
        if (active) setEnabled(p.guide_enabled);
      })
      .catch((e) => {
        if (active) setError(String(e));
      });
    return () => {
      active = false;
    };
  }, [revision]);
  async function toggle() {
    setBusy(true);
    try {
      const p = await call<Preferences>("/me/learning-preferences", {
        method: "PATCH",
        body: JSON.stringify({ guide_enabled: !enabled }),
      });
      setEnabled(p.guide_enabled);
      setError("");
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const steps = [
    "Tạo hoặc chọn môn học.",
    "Tải đề cương PDF hoặc dán nội dung.",
    "Kiểm tra các tuần học rồi xác nhận.",
    "Duyệt lộ trình và mở đồ thị.",
    "Chọn một chặng để đọc và ghim nguồn.",
  ];
  return (
    <section aria-label="Hướng dẫn bắt đầu" className="core-panel card learning-guide">
      {error ? (
        <p role="status">
          Không tải được hướng dẫn.{" "}
          <button onClick={() => retry((v) => v + 1)}>Thử tải hướng dẫn</button>
        </p>
      ) : enabled === null ? (
        <p role="status">Đang tải hướng dẫn…</p>
      ) : (
        <>
          {enabled && (
            <>
              <h2>Bắt đầu học</h2>
              <progress
                aria-label="Tiến trình bắt đầu"
                value={step}
                max={5}
              />{" "}
              <strong>Bước {step}/5</strong>
              <p>{steps[step - 1]}</p>
            </>
          )}
          <button disabled={busy} onClick={toggle}>
            {enabled ? "Bỏ qua hướng dẫn" : "Xem hướng dẫn"}
          </button>
        </>
      )}
    </section>
  );
}
