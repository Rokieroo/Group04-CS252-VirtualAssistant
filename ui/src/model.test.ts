import { describe, it, expect } from "vitest";
import {
  initialState,
  enroll,
  saveFuture,
  verify,
  progress,
  completion,
  balance,
  pendingCount,
  verifiedCount,
} from "./model";
describe("learning state invariants", () => {
  it("saving a course does not enroll it or schedule sessions", () => {
    const before = initialState();
    const after = saveFuture(before, "biology");
    expect(after.active).toEqual(before.active);
    expect(after.sessions).toEqual(before.sessions);
    expect(after.future).toEqual(["biology"]);
    expect(saveFuture(after, "biology").future).toHaveLength(1);
  });
  it("enrollment creates sessions once and removes the saved request", () => {
    const saved = saveFuture(initialState(), "math");
    const active = enroll(saved, "math");
    expect(active.future).toEqual([]);
    expect(active.sessions.length).toBe(saved.sessions.length + 3);
    expect(enroll(active, "math")).toBe(active);
  });
  it("failed checks never award progress and retakes cannot duplicate credit", () => {
    const s = initialState();
    expect(completion(s, "english")).toEqual({
      verified: 6,
      total: 13,
      percent: 46,
      baseline: 6,
    });
    expect(verify(s, "past", 50)).toBe(s);
    expect(verify(s, "missing", 100)).toBe(s);
    const passed = verify(s, "past", 75);
    expect(completion(passed, "english")).toMatchObject({
      verified: 7,
      total: 13,
      percent: 53,
    });
    expect(progress(passed, "english")).toBe(53);
    expect(verify(passed, "past", 100)).toBe(passed);
    const fullyVerified = s.sessions.reduce(
      (current, session) => verify(current, session.id, 100),
      s,
    );
    expect(completion(fullyVerified, "english")).toMatchObject({
      verified: 13,
      total: 13,
      percent: 100,
    });
  });
  it("workload changes preserve verified sessions and future plans", () => {
    const s = verify(saveFuture(initialState(), "biology"), "past", 100);
    const after = balance(s, 2);
    expect(after.sessions.find((x) => x.id === "past")).toEqual(
      s.sessions.find((x) => x.id === "past"),
    );
    expect(after.future).toEqual(["biology"]);
    expect(after.verified).toEqual(["past"]);
  });
  it("keeps assessment totals scoped to the selected course", () => {
    const englishPassed = verify(initialState(), "past", 100);
    const withMath = enroll(englishPassed, "math");
    expect(verifiedCount(withMath, "english")).toBe(1);
    expect(verifiedCount(withMath, "math")).toBe(0);
    expect(pendingCount(withMath, "math")).toBe(0);
    expect(completion(withMath, "math")).toMatchObject({
      verified: 0,
      total: 3,
      percent: 0,
    });
    expect(completion(verify(withMath, "math-0", 100), "math")).toMatchObject({
      verified: 1,
      total: 3,
      percent: 33,
    });
  });
});
