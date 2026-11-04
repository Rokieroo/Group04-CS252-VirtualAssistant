import { useRef, useState } from "react";
import { currentCourse } from "../../api/courses";

type Props = {
  busy: boolean;
  mock: boolean;
  onUpload: (input: File | string) => void;
};

/** S3: selecting input and submitting it are separate, deliberate actions. */
export function SyllabusUpload({ busy, mock, onUpload }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [text, setText] = useState("");
  const [paste, setPaste] = useState(false);
  return (
    <>
      <div className="core-setup-columns">
        <section
          className="card core-panel core-upload"
          aria-labelledby="s3-title"
        >
          <h2 id="s3-title">Course details</h2>
          <label>
            Course name
            <input value={currentCourse.name} readOnly />
          </label>
          <div>
            <span className="core-field-label">Syllabus file</span>
            <div
              className="core-drop"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                if (!busy && e.dataTransfer.files[0]) {
                  setFile(e.dataTransfer.files[0]);
                  setPaste(false);
                }
              }}
            >
              <span className="core-upload-icon" aria-hidden="true">
                ↑
              </span>
              <strong>
                {file ? file.name : "Drop your syllabus file here"}
              </strong>
              <p>Supported formats: PDF and DOCX (up to 20 MB)</p>
              <input
                ref={input}
                type="file"
                hidden
                accept=".pdf,.docx"
                aria-label="Syllabus file"
                onChange={(e) => {
                  setFile(e.target.files?.[0] ?? null);
                  setPaste(false);
                }}
              />
              <button
                className="primary-action"
                disabled={busy}
                onClick={() => input.current?.click()}
              >
                Select a file
              </button>
            </div>
          </div>
          <button
            className="core-text-button"
            disabled={busy}
            aria-expanded={paste}
            onClick={() => setPaste(!paste)}
          >
            Prefer text? Paste your syllabus instead
          </button>
          {paste && (
            <label>
              Syllabus text
              <textarea
                disabled={busy}
                maxLength={120000}
                rows={6}
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Paste learning outcomes, weekly topics and assessments…"
              />
            </label>
          )}
          <p className="hint">
            We keep page references so extracted data can be verified.
          </p>
          {mock ? (
            <p className="hint">
              Preview uses a sample syllabus. Your file is not parsed or
              uploaded.
            </p>
          ) : (
            <p className="hint">
              PDF/DOCX and pasted text are parsed for your review before saving.
            </p>
          )}
        </section>
        <aside className="card core-panel core-setup-aside">
          <h3>What happens next?</h3>
          <ol className="core-next-steps">
            <li>
              <span>01</span>
              <div>
                <strong>Upload</strong>
                <p>Choose PDF, DOCX or paste text.</p>
              </div>
            </li>
            <li>
              <span>02</span>
              <div>
                <strong>Review</strong>
                <p>Verify weeks, outcomes and assessments.</p>
              </div>
            </li>
            <li>
              <span>03</span>
              <div>
                <strong>Generate</strong>
                <p>Approve a personalized study roadmap.</p>
              </div>
            </li>
          </ol>
          <div className="core-control-note">
            <strong>✓ You stay in control</strong>
            <p>
              The AI proposes a draft. You can edit everything before approving
              your roadmap.
            </p>
          </div>
        </aside>
      </div>
      <div className="core-upload-footer">
        <span>Upload → Review → Approve</span>
        <button
          className="primary-action"
          disabled={busy || (paste ? !text.trim() : !file)}
          onClick={() => {
            const value = paste ? text : file;
            if (value) onUpload(value);
          }}
        >
          Continue to review →
        </button>
      </div>
    </>
  );
}
