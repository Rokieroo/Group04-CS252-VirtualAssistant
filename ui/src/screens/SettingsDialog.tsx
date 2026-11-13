import { useState, type FormEvent } from "react";
import type { User } from "../api";
import { call } from "../api/backend";
import { explain } from "../app/text";
import { applyTheme, loadTheme, saveTheme, themes, type Theme } from "../app/theme";
import { Button, Dialog, Field, Notice } from "../ui/kit";

const styles = [
  ["warm", "Ấm áp"],
  ["direct", "Thẳng thắn"],
  ["playful", "Vui nhộn"],
] as const;

/** Appearance on this device, and for a signed-in learner the profile and the way out. */
export function SettingsDialog({
  user,
  onUser,
  onSignOut,
  onClose,
}: {
  /** Absent in the preview, which has no account. */
  user: User | null;
  onUser: (user: User) => void;
  onSignOut: () => void;
  onClose: () => void;
}) {
  const [theme, setTheme] = useState<Theme>(loadTheme);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: "success" | "error"; text: string } | null>(null);

  const pick = (next: Theme) => {
    setTheme(next);
    saveTheme(next);
    applyTheme(next);
  };
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setNote(null);
    try {
      onUser(
        await call<User>("/me", {
          method: "PATCH",
          body: JSON.stringify({
            name: form.get("name"),
            timezone: form.get("timezone"),
            personality: form.get("personality"),
          }),
        }),
      );
      setNote({ tone: "success", text: "Đã lưu hồ sơ." });
    } catch (e) {
      setNote({ tone: "error", text: explain(e) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog title="Cài đặt" onClose={onClose}>
      <fieldset>
        <legend className="field-label">Giao diện</legend>
        <div className="segmented" role="group" aria-label="Giao diện">
          {themes.map((t) => (
            <button key={t.id} type="button" aria-pressed={theme === t.id} onClick={() => pick(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
      </fieldset>

      {user && (
        <>
          <hr className="rule" />
          <form className="stack" onSubmit={save}>
            <Field label="Tên hiển thị">
              <input name="name" defaultValue={user.name} required maxLength={80} autoComplete="name" />
            </Field>
            <Field label="Múi giờ của lịch" hint="Ví dụ: Asia/Ho_Chi_Minh">
              <input name="timezone" defaultValue={user.timezone} required />
            </Field>
            <Field label="Phong cách của bạn học">
              <select name="personality" defaultValue={user.personality}>
                {styles.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </Field>
            {note && <Notice tone={note.tone}>{note.text}</Notice>}
            <div className="row">
              <Button type="submit" variant="primary" disabled={busy}>
                Lưu hồ sơ
              </Button>
              <span className="muted small grow">{user.email}</span>
            </div>
          </form>
          <hr className="rule" />
          <div>
            <Button variant="danger" icon="logout" onClick={onSignOut}>
              Đăng xuất
            </Button>
          </div>
        </>
      )}
    </Dialog>
  );
}
