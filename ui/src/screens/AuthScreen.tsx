import { useState, type FormEvent } from "react";
import { authenticate } from "../api/account";
import { BackendError } from "../api/backend";
import { explain } from "../app/text";
import { validateAuth, type AuthErrors, type AuthForm } from "../auth";
import { Icon } from "../ui/icons";
import { Button, Field, Notice } from "../ui/kit";

const promise = ["Đưa đề cương vào", "Kiểm tra nội dung", "Nhận lộ trình theo tuần", "Học theo lịch của bạn"];

/** Sign in or register (S1). The session token stays in this tab. */
export function AuthScreen({ onAuth }: { onAuth: (token: string) => void }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState<AuthForm>({ email: "", password: "", birthYear: "", level: "university" });
  const [errors, setErrors] = useState<AuthErrors>({});
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: keyof AuthForm, value: string) => setForm((f) => ({ ...f, [key]: value }));
  const login = mode === "login";

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    const found = validateAuth(form, mode);
    setErrors(found);
    setFailure("");
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      onAuth((await authenticate(form, mode)).token);
    } catch (e) {
      // At this door a 401 is a wrong password, not an expired session.
      const status = e instanceof BackendError ? e.status : -1;
      setFailure(
        status === 401
          ? "Email hoặc mật khẩu không đúng."
          : status === 409
            ? "Email này đã có tài khoản. Hãy đăng nhập."
            : explain(e),
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="auth">
      <section className="auth-side" aria-label="Pathly làm gì">
        <p className="brand">
          <span className="brand-mark">
            <Icon name="roadmap" size={26} />
          </span>
          Pathly
        </p>
        <h1>Từ đề cương môn học đến lộ trình bạn theo được.</h1>
        <ol className="auth-route">
          {promise.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ol>
      </section>

      <form className="auth-form" onSubmit={submit} noValidate>
        <h2>{login ? "Đăng nhập" : "Tạo tài khoản"}</h2>
        <Field label="Email" error={errors.email}>
          <input
            type="email"
            autoComplete="email"
            value={form.email}
            aria-invalid={Boolean(errors.email)}
            onChange={(event) => set("email", event.target.value)}
          />
        </Field>
        <Field label="Mật khẩu" error={errors.password} hint={login ? undefined : "Ít nhất 8 ký tự."}>
          <input
            type="password"
            autoComplete={login ? "current-password" : "new-password"}
            value={form.password}
            aria-invalid={Boolean(errors.password)}
            onChange={(event) => set("password", event.target.value)}
          />
        </Field>
        {!login && (
          <>
            <Field label="Năm sinh" error={errors.birthYear}>
              <input
                type="number"
                inputMode="numeric"
                autoComplete="bday-year"
                value={form.birthYear}
                aria-invalid={Boolean(errors.birthYear)}
                onChange={(event) => set("birthYear", event.target.value)}
              />
            </Field>
            <Field label="Bạn đang học">
              <select value={form.level} onChange={(event) => set("level", event.target.value)}>
                <option value="university">Đại học</option>
                <option value="k12">Phổ thông</option>
              </select>
            </Field>
          </>
        )}
        {failure && <Notice tone="error">{failure}</Notice>}
        <Button type="submit" variant="primary" disabled={busy}>
          {busy ? "Đang xử lý…" : login ? "Đăng nhập" : "Tạo tài khoản"}
        </Button>
        <Button
          variant="quiet"
          onClick={() => {
            setMode(login ? "register" : "login");
            setErrors({});
            setFailure("");
          }}
        >
          {login ? "Chưa có tài khoản? Tạo tài khoản" : "Đã có tài khoản? Đăng nhập"}
        </Button>
      </form>
    </main>
  );
}
