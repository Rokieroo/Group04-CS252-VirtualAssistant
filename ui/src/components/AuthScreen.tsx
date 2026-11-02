import { useState, type FormEvent } from "react";
import type { Authenticate } from "../api/account";
import { validateAuth, type AuthErrors, type AuthForm } from "../auth";

/** S1 Sign in / Register. The token goes to the caller, which keeps it in memory only. */
export function AuthScreen({
  onAuth,
  authenticate,
}: {
  onAuth: (token: string) => void;
  authenticate: Authenticate;
}) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState<AuthForm>({
    email: "",
    password: "",
    birthYear: "",
    level: "university",
  });
  const [errors, setErrors] = useState<AuthErrors>({});
  const [failure, setFailure] = useState("");
  const [busy, setBusy] = useState(false);
  const set = (key: keyof AuthForm, value: string) =>
    setForm((f) => ({ ...f, [key]: value }));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const found = validateAuth(form, mode);
    setErrors(found);
    setFailure("");
    if (Object.keys(found).length) return;
    setBusy(true);
    try {
      onAuth((await authenticate(form, mode)).token);
    } catch (err) {
      setFailure(err instanceof Error ? err.message : "Sign-in failed.");
    } finally {
      setBusy(false);
    }
  };

  const field = (
    key: "email" | "password" | "birthYear",
    label: string,
    type: string,
  ) => (
    <label className="auth-field">
      <span id={`${key}-label`}>{label}</span>
      <input
        type={type}
        aria-labelledby={`${key}-label`}
        value={form[key]}
        onChange={(e) => set(key, e.target.value)}
        aria-invalid={!!errors[key]}
        aria-describedby={errors[key] ? `${key}-error` : undefined}
        autoComplete={
          key === "email"
            ? "email"
            : key === "password"
              ? mode === "login"
                ? "current-password"
                : "new-password"
              : "off"
        }
      />
      {errors[key] && (
        <span id={`${key}-error`} className="auth-error">
          {errors[key]}
        </span>
      )}
    </label>
  );

  return (
    <main className="auth">
      <form className="auth-card" onSubmit={submit} noValidate>
        <div className="brand auth-brand">
          <span>✦</span> pathly
        </div>
        <h1>{mode === "login" ? "Sign in" : "Create account"}</h1>
        {field("email", "Email", "email")}
        {field("password", "Password", "password")}
        {mode === "register" && (
          <>
            {field("birthYear", "Birth year", "number")}
            <label className="auth-field">
              Education level
              <select
                value={form.level}
                onChange={(e) => set("level", e.target.value)}
              >
                <option value="university">University</option>
                <option value="k12">School (K-12)</option>
              </select>
            </label>
          </>
        )}
        {failure && (
          <p role="alert" className="auth-error">
            {failure}
          </p>
        )}
        <button className="auth-submit" type="submit" disabled={busy}>
          {busy ? "Working…" : mode === "login" ? "Sign in" : "Register"}
        </button>
        <button
          type="button"
          className="auth-switch"
          onClick={() => {
            setMode(mode === "login" ? "register" : "login");
            setErrors({});
            setFailure("");
          }}
        >
          {mode === "login"
            ? "No account yet? Register"
            : "Already have an account? Sign in"}
        </button>
      </form>
    </main>
  );
}
