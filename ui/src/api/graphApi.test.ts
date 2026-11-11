import { afterEach, it, expect, vi } from "vitest";
import { call, BackendError } from "./backend";
afterEach(() => vi.unstubAllGlobals());
it("retains the structured server cycle path for the canvas", async () => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValue(
        new Response(
          JSON.stringify({ detail: { error: "cycle", path: ["a", "b", "a"] } }),
          { status: 409, headers: { "Content-Type": "application/json" } },
        ),
      ),
  );
  await expect(
    call("/roadmaps/rm/graph/edges", {
      method: "POST",
      body: JSON.stringify({ parent_id: "b", child_id: "a", kind: "strict" }),
    }),
  ).rejects.toMatchObject({
    status: 409,
    detail: { path: ["a", "b", "a"] },
  } satisfies Partial<BackendError>);
});
