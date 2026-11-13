export type Level = "university" | "k12";
export type AuthForm = {
  email: string;
  password: string;
  birthYear: string;
  level: Level;
  /** A parent or guardian agreed; the server refuses to register a learner under 18 without it. */
  consent?: boolean;
};
export type AuthErrors = Partial<Record<keyof AuthForm, string>>;

const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/** Same rule as POST /auth/register: calendar years only, so it matches the server exactly. */
export const isMinor = (birthYear: string, now = new Date()) =>
  Number(birthYear) > 0 && now.getFullYear() - Number(birthYear) < 18;

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
    else if (isMinor(form.birthYear, now) && !form.consent)
      errors.consent = "Bạn dưới 18 tuổi nên cần cha mẹ hoặc người giám hộ đồng ý.";
  }
  return errors;
}
