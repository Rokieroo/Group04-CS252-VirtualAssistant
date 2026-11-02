import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Call = { method: string; path: string; body: unknown; auth: string | null };
const BASE = "http://api.test";
const pdf = () => new File(["%PDF-1.7"], "week01.pdf", { type: "application/pdf" });

/** api/courses.ts and api/mock.ts in VITE_BACKEND_MODE=api, with fetch answered by `reply`. */
async function live(reply: (call: Call) => Response) {
  vi.stubEnv("VITE_BACKEND_MODE", "api");
  vi.stubEnv("VITE_API_URL", BASE);
  const store = new Map<string, string>();
  vi.stubGlobal("sessionStorage", {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => store.set(key, value),
    removeItem: (key: string) => store.delete(key),
  });
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      const headers = (init.headers ?? {}) as Record<string, string>;
      const call = {
        method: init.method ?? "GET",
        path: url.slice(BASE.length),
        body: typeof init.body === "string" ? JSON.parse(init.body) : init.body,
        auth: headers.Authorization ?? null,
      };
      calls.push(call);
      return reply(call);
    }),
  );
  vi.resetModules();
  const courses = await import("./courses");
  const mock = await import("./mock");
  return { ...courses, authenticate: mock.authenticate, calls, store };
}

const concept = {
  id: "c1",
  slug: "solution-ladder",
  title: "Solution ladder",
  summary: "Chỉ leo tới bậc thấp nhất đủ dùng.",
  bloom_level: "understand",
  source_pages: [77],
  confirmed: false,
};

const item = {
  id: "i1",
  type: "mcq",
  prompt: "Bậc nào dùng BM25?",
  choices: ["Rules", "Search (BM25)", "ML", "LLM"],
  answer: "Search (BM25)",
  rubric: [],
  source_id: "s77",
  page: 77,
  file_name: "week01.pdf",
  status: "draft",
};

function happyBackend({ method, path }: Call): Response {
  if (path === "/api/v1/auth/register")
    return Response.json({ access_token: "tok-1" }, { status: 201 });
  if (path === "/api/v1/courses" && method === "GET") return Response.json([]);
  if (path === "/api/v1/courses") return Response.json({ id: "course-1" }, { status: 201 });
  if (path.endsWith("/sources"))
    return Response.json(
      { file_name: "week01.pdf", pages: 3, status: "processed", warning: null },
      { status: 201 },
    );
  if (path.includes("concepts:propose")) return Response.json({ concepts: [concept], prereqs: [] });
  if (path.endsWith("items:generate")) return Response.json([item], { status: 201 });
  return Response.json({ detail: "unexpected" }, { status: 500 });
}

beforeEach(() => vi.unstubAllEnvs());
afterEach(() => vi.unstubAllGlobals());

describe("concept extraction against the real backend", () => {
  it("registers, finds-or-creates the course once, uploads and proposes per file", async () => {
    const api = await live(happyBackend);
    const form = { email: " ana@uni.test ", password: "pass-1234", birthYear: "2005", level: "university" as const };
    expect(await api.authenticate(form, "register")).toEqual({ token: "tok-1" });
    expect(api.calls[0].body).toEqual({
      email: "ana@uni.test",
      password: "pass-1234",
      name: "ana",
      birth_year: 2005,
      account_level: "university",
    });
    expect(api.store.get("pathly.session")).toBe("tok-1");

    expect(await api.uploadSource("CSC10014", pdf())).toEqual({
      file_name: "week01.pdf",
      pages: 3,
      status: "processed",
      warning: undefined,
    });
    const graph = await api.proposeConcepts("CSC10014", "week 01.pdf");
    expect(graph.concepts).toEqual([{ ...concept, source_file: "" }]);

    expect(api.calls.slice(1).map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /api/v1/courses",
      "POST /api/v1/courses",
      "POST /api/v1/courses/course-1/sources",
      "POST /api/v1/courses/course-1/concepts:propose?file_name=week%2001.pdf",
    ]);
    expect(api.calls[2].body).toEqual({ title: "CSC10014" });
    expect((api.calls[3].body as FormData).get("file")).toBeInstanceOf(File);
    expect(api.calls.slice(1).every((c) => c.auth === "Bearer tok-1")).toBe(true);
  });

  it("generates cited questions for a stored concept", async () => {
    const api = await live(happyBackend);
    expect(await api.generateItems("CSC10014", "c/1")).toEqual([item]);
    expect(api.calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /api/v1/courses",
      "POST /api/v1/courses",
      "POST /api/v1/courses/course-1/concepts/c%2F1/items:generate",
    ]);
  });

  it("turns a refused generation into items_unavailable", async () => {
    const api = await live((call) =>
      call.path.endsWith("items:generate")
        ? Response.json({ detail: "items_unavailable" }, { status: 503 })
        : happyBackend(call),
    );
    await expect(api.generateItems("CSC10014", "c1")).rejects.toEqual(
      new api.ApiError("items_unavailable"),
    );
  });

  it("reuses an existing course with the same title", async () => {
    const api = await live((call) =>
      call.path === "/api/v1/courses"
        ? Response.json([{ id: "old", title: "CSC10014" }])
        : happyBackend(call),
    );
    await api.uploadSource("CSC10014", pdf());
    expect(api.calls.map((c) => `${c.method} ${c.path}`)).toEqual([
      "GET /api/v1/courses",
      "POST /api/v1/courses/old/sources",
    ]);
  });

  it("turns known backend codes into ApiError and keeps other messages", async () => {
    const api = await live((call) =>
      call.path.includes("concepts:propose")
        ? Response.json({ detail: "concepts_unavailable" }, { status: 503 })
        : call.path.endsWith("/sources")
          ? Response.json({ detail: "Something odd" }, { status: 500 })
          : happyBackend(call),
    );
    await expect(api.proposeConcepts("CSC10014", "week01.pdf")).rejects.toEqual(
      new api.ApiError("concepts_unavailable"),
    );
    await expect(api.uploadSource("CSC10014", pdf())).rejects.toThrow("Something odd");
  });

  it("ends the session on 401 and explains an unreachable server", async () => {
    const api = await live(() => Response.json({ detail: "expired" }, { status: 401 }));
    api.store.set("pathly.session", "stale");
    await expect(api.uploadSource("CSC10014", pdf())).rejects.toThrow("sign in again");
    expect(api.store.has("pathly.session")).toBe(false);

    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(api.uploadSource("CSC10014", pdf())).rejects.toThrow("Cannot reach the server");
  });

  it("still rejects a non-PDF before any request", async () => {
    const api = await live(happyBackend);
    const text = new File(["hi"], "notes.txt", { type: "text/plain" });
    await expect(api.uploadSource("CSC10014", text)).rejects.toEqual(new api.ApiError("not_pdf"));
    expect(api.calls).toEqual([]);
  });
});
