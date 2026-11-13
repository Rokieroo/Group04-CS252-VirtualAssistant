export type Level = "university" | "k12";
export type AuthForm = {
  email: string;
  password: string;
  birthYear: string;
  level: Level;
};
export type AuthErrors = Partial<Record<keyof AuthForm, string>>;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Client-side checks for spec S1. Login only needs email + password. */
export function validateAuth(
  form: AuthForm,
  mode: "login" | "register",
  now = new Date(),
): AuthErrors {
  const errors: AuthErrors = {};
  if (!EMAIL.test(form.email.trim())) errors.email = "Hãy nhập một địa chỉ email hợp lệ.";
  if (form.password.length < 8) errors.password = "Mật khẩu cần ít nhất 8 ký tự.";
  if (mode === "register") {
    const year = Number(form.birthYear);
    if (!Number.isInteger(year) || year < 1900 || year > now.getFullYear())
      errors.birthYear = `Năm sinh phải từ 1900 đến ${now.getFullYear()}.`;
  }
  return errors;
}
