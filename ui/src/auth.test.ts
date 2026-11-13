import { describe, expect, it } from "vitest";
import { validateAuth, type AuthForm } from "./auth";

const ok: AuthForm = {
  email: "lan@student.hcmus.edu.vn",
  password: "12345678",
  birthYear: "2006",
  level: "university",
};
const now = new Date("2026-10-27");

describe("validateAuth", () => {
  it("accepts a valid registration", () => {
    expect(validateAuth(ok, "register", now)).toEqual({});
  });
  it("rejects an invalid email", () => {
    expect(validateAuth({ ...ok, email: "lan@" }, "register", now).email).toBeTruthy();
  });
  it("rejects a password under 8 characters", () => {
    expect(validateAuth({ ...ok, password: "1234567" }, "login", now).password).toBeTruthy();
  });
  it("rejects birth years outside 1900..current year", () => {
    for (const birthYear of ["1899", "2027", "abc", ""])
      expect(validateAuth({ ...ok, birthYear }, "register", now).birthYear).toBeTruthy();
    expect(validateAuth({ ...ok, birthYear: "1900" }, "register", now)).toEqual({});
    expect(validateAuth({ ...ok, birthYear: "2026", consent: true }, "register", now)).toEqual({});
  });
  it("asks for guardian consent under 18, by calendar year like the server", () => {
    expect(validateAuth({ ...ok, birthYear: "2009" }, "register", now).consent).toBeTruthy();
    expect(validateAuth({ ...ok, birthYear: "2009", consent: true }, "register", now)).toEqual({});
    expect(validateAuth({ ...ok, birthYear: "2008" }, "register", now)).toEqual({});
  });
  it("does not require a birth year to log in", () => {
    expect(validateAuth({ ...ok, birthYear: "" }, "login", now)).toEqual({});
  });
});
