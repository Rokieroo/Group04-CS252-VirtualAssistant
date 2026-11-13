import { validateAuth, type AuthForm } from "../auth";
import { call, session } from "./backend";

/** Signs in or registers; the demo passes its own fake one to AuthScreen. */
export type Authenticate = (
  form: AuthForm,
  mode: "login" | "register",
) => Promise<{ token: string }>;

export function assertValid(form: AuthForm, mode: "login" | "register") {
  if (Object.keys(validateAuth(form, mode)).length)
    throw new Error("Please fix the highlighted fields.");
}

/** Signs in or registers against the backend and keeps the session for this tab. */
export const authenticate: Authenticate = async (form, mode) => {
  assertValid(form, mode);
  const email = form.email.trim();
  const body =
    mode === "login"
      ? { email, password: form.password }
      : {
          email,
          password: form.password,
          // shortcut: S1 asks for no name; use the email's local part until a name field exists.
          name: email.split("@")[0],
          birth_year: Number(form.birthYear),
          account_level: form.level,
          parental_consent: Boolean(form.consent),
        };
  const auth = await call<{ access_token: string }>(
    mode === "login" ? "/auth/login" : "/auth/register",
    { method: "POST", body: JSON.stringify(body) },
  );
  session.set(auth.access_token);
  return { token: auth.access_token };
};
