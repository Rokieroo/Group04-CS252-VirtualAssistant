// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CoreJourney } from "./CoreJourney";

function makeDeferred<T>() {
  let resolve!: (val: T) => void;
  let reject!: (err: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("CoreJourney Knowledge Graph loading & edge choices", () => {
  beforeEach(() => {
    sessionStorage.setItem("pathly.session", "test-token");
    HTMLDialogElement.prototype.showModal = vi.fn(function (
      this: HTMLDialogElement,
    ) {
      this.open = true;
    });
    HTMLDialogElement.prototype.close = vi.fn();
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    sessionStorage.clear();
    history.replaceState(null, "", "/");
  });

  it("keeps authoritative graph visible when layout loading fails and recovers via layout retry", async () => {
    history.replaceState(
      null,
      "",
      "/?kg_roadmap=rm-1&kg_viewMode=list#roadmap",
    );
    let layoutAttempt = 0;

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/roadmaps/rm-1")) {
          return new Response(
            JSON.stringify({
              id: "rm-1",
              course_id: "c1",
              nodes: [
                { id: "a", title: "Draft Node", type: "topic", week: 1 },
              ],
              edges: [],
            }),
            { status: 200 },
          );
        }
        if (url.endsWith("/roadmaps/rm-1/edges")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.endsWith("/roadmaps/rm-1/graph")) {
          return new Response(
            JSON.stringify({
              nodes: [
                {
                  id: "a",
                  title: "Authoritative Topic",
                  type: "topic",
                  week: 1,
                  status: "mastered",
                  sources_status: "ready",
                },
                {
                  id: "m1",
                  title: "Midterm Milestone",
                  type: "milestone",
                  week: 2,
                },
              ],
              edges: [
                {
                  parent: "a",
                  child: "m1",
                  kind: "covers",
                  origin: "milestone_covers",
                  confidence: 1,
                },
              ],
            }),
            { status: 200 },
          );
        }
        if (url.endsWith("/roadmaps/rm-1/graph/layout")) {
          layoutAttempt += 1;
          if (layoutAttempt === 1) {
            return new Response(
              JSON.stringify({ detail: "layout timeout" }),
              { status: 500 },
            );
          }
          return new Response(
            JSON.stringify({
              positions: [{ node_id: "a", x: 320, y: 180, pinned: true }],
              saved: 1,
            }),
            { status: 200 },
          );
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }),
    );

    render(<CoreJourney page="Roadmap" go={vi.fn()} />);

    // Authoritative graph node renders even though /graph/layout failed.
    await screen.findByRole("button", {
      name: "Chọn chặng Authoritative Topic",
    });
    expect(
      await screen.findByRole("button", { name: "Thử tải lại vị trí" }),
    ).toBeTruthy();
    expect(
      screen.queryByRole("button", { name: "Retry graph loading" }),
    ).toBeNull();

    // Retry layout loading recovers cleanly without re-failing graph.
    fireEvent.click(screen.getByRole("button", { name: "Thử tải lại vị trí" }));
    await waitFor(() => {
      expect(
        screen.queryByRole("button", { name: "Thử tải lại vị trí" }),
      ).toBeNull();
    });
    expect(layoutAttempt).toBe(2);
  });

  it("exposes graph-specific error and retry when graph fetch fails independently of layout", async () => {
    history.replaceState(
      null,
      "",
      "/?kg_roadmap=rm-err&kg_viewMode=list#roadmap",
    );
    let graphAttempts = 0;

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.endsWith("/roadmaps/rm-err")) {
          return new Response(
            JSON.stringify({
              id: "rm-err",
              course_id: "c1",
              nodes: [{ id: "a", title: "Fallback Node", type: "topic", week: 1 }],
              edges: [],
            }),
            { status: 200 },
          );
        }
        if (url.endsWith("/roadmaps/rm-err/edges")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.endsWith("/roadmaps/rm-err/graph")) {
          graphAttempts += 1;
          if (graphAttempts === 1) {
            return new Response(
              JSON.stringify({ detail: "graph_unavailable" }),
              { status: 503 },
            );
          }
          return new Response(
            JSON.stringify({
              nodes: [{ id: "a", title: "Recovered Graph Node", type: "topic", week: 1 }],
              edges: [],
            }),
            { status: 200 },
          );
        }
        if (url.endsWith("/roadmaps/rm-err/graph/layout")) {
          return new Response(JSON.stringify({ positions: [], saved: 0 }), { status: 200 });
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }),
    );

    render(<CoreJourney page="Roadmap" go={vi.fn()} />);

    const retryGraph = await screen.findByRole("button", {
      name: "Retry graph loading",
    });
    expect(
      screen.queryByRole("button", { name: "Thử tải lại vị trí" }),
    ).toBeNull();

    fireEvent.click(retryGraph);
    await screen.findByRole("button", {
      name: "Chọn chặng Recovered Graph Node",
    });
    expect(
      screen.queryByRole("button", { name: "Retry graph loading" }),
    ).toBeNull();
  });

  it("ignores slow responses from an earlier roadmap after switching to a newer roadmap", async () => {
    const slowGraph = makeDeferred<Response>();
    const slowLayout = makeDeferred<Response>();
    let generateCalls = 0;

    vi.stubGlobal(
      "fetch",
      vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/courses/c1/syllabus")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id: "syl-1",
                syllabus_id: "syl-1",
                course_id: "c1",
                status: "confirmed",
                raw_text: JSON.stringify({
                  file_name: "course.txt",
                  course: { title: { value: "Graph course" } },
                  weeks: [{ week: 1, topics: ["Intro"], source_page: 1 }],
                  outcomes: [{ code: "CLO1", description: "Intro", source_page: 1 }],
                  assessments: [{ name: "Exam", weight: 100, due_week: 2, source_page: 1 }],
                }),
                learning_outcomes: [{ id: "o1", code: "CLO1", description: "Intro" }],
                assessments: [{ id: "a1", name: "Exam", weight: 100, due_week: 2 }],
              }),
              { status: 200 },
            ),
          );
        }
        if (url.includes("/roadmap:generate") && init?.method === "POST") {
          generateCalls += 1;
          const id = generateCalls === 1 ? "rm-slow" : "rm-fast";
          return Promise.resolve(
            new Response(
              JSON.stringify({
                id,
                roadmap_id: id,
                course_id: "c1",
                title: "Graph course",
                nodes: [
                  {
                    id: id === "rm-slow" ? "s1" : "f1",
                    title: id === "rm-slow" ? "Slow Seed" : "Fast Seed",
                    type: "topic",
                    week: 1,
                  },
                ],
                edges: [],
              }),
              { status: 201 },
            ),
          );
        }
        if (url.endsWith("/roadmaps/rm-slow/graph")) {
          return slowGraph.promise;
        }
        if (url.endsWith("/roadmaps/rm-slow/graph/layout")) {
          return slowLayout.promise;
        }
        if (url.endsWith("/roadmaps/rm-fast/graph")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                nodes: [
                  { id: "f1", title: "Fast Active Topic", type: "topic", week: 1 },
                ],
                edges: [],
              }),
              { status: 200 },
            ),
          );
        }
        if (url.endsWith("/roadmaps/rm-fast/graph/layout")) {
          return Promise.resolve(
            new Response(
              JSON.stringify({
                positions: [{ node_id: "f1", x: 500, y: 250, pinned: true }],
                saved: 1,
              }),
              { status: 200 },
            ),
          );
        }
        return Promise.resolve(new Response(JSON.stringify([]), { status: 200 }));
      }),
    );

    render(<CoreJourney page="Library" go={vi.fn()} courseId="c1" resumeSyllabus />);

    // 1. Generate first roadmap (rm-slow) and open its Graph tab while graph/layout stay in flight.
    fireEvent.click(await screen.findByRole("button", { name: "Tạo roadmap →" }));
    fireEvent.click(await screen.findByRole("tab", { name: "Graph tiên quyết" }));
    expect(screen.getByRole("button", { name: "Slow Seed" })).toBeTruthy();

    // 2. Switch to a second roadmap (rm-fast) in the same mounted CoreJourney instance.
    fireEvent.click(screen.getByRole("button", { name: "← Quay lại sửa đề cương" }));
    fireEvent.click(await screen.findByRole("button", { name: "Tạo roadmap →" }));
    await screen.findByRole("tab", { name: "Graph tiên quyết" });
    await screen.findByRole("button", { name: "Danh sách" });
    fireEvent.click(screen.getByRole("button", { name: "Danh sách" }));
    await screen.findByRole("button", { name: "Chọn chặng Fast Active Topic" });

    // 3. Resolve rm-slow's stale responses AFTER rm-fast is active; rm-fast must not be overwritten.
    slowGraph.resolve(
      new Response(
        JSON.stringify({
          nodes: [{ id: "s1", title: "Stale Slow Topic", type: "topic", week: 1 }],
          edges: [],
        }),
        { status: 200 },
      ),
    );
    slowLayout.resolve(
      new Response(
        JSON.stringify({
          positions: [{ node_id: "s1", x: 999, y: 999, pinned: true }],
          saved: 1,
        }),
        { status: 200 },
      ),
    );

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "Chọn chặng Fast Active Topic" })).toBeTruthy();
      expect(screen.queryByRole("button", { name: "Chọn chặng Stale Slow Topic" })).toBeNull();
    });
  });

  it("offers milestones in prerequisite selects, blocks self-edges and cycles through milestone covers, and submits valid milestone edges", async () => {
    history.replaceState(
      null,
      "",
      "/?kg_roadmap=rm-m&kg_viewMode=list#roadmap",
    );
    const created: Array<{ parent_id: string; child_id: string }> = [];

    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        const url = String(input);
        if (url.endsWith("/roadmaps/rm-m")) {
          return new Response(
            JSON.stringify({
              id: "rm-m",
              course_id: "c1",
              nodes: [
                { id: "t1", title: "Topic One", type: "topic", week: 1 },
                { id: "t2", title: "Topic Two", type: "topic", week: 3 },
                { id: "m1", title: "Midterm Quiz", type: "milestone", week: 2, covers: ["t1"] },
              ],
              edges: [],
            }),
            { status: 200 },
          );
        }
        if (url.endsWith("/roadmaps/rm-m/edges")) {
          return new Response(JSON.stringify([]), { status: 200 });
        }
        if (url.endsWith("/roadmaps/rm-m/graph")) {
          return new Response(
            JSON.stringify({
              nodes: [
                { id: "t1", title: "Topic One", type: "topic", week: 1 },
                { id: "t2", title: "Topic Two", type: "topic", week: 3 },
                { id: "m1", title: "Midterm Quiz", type: "milestone", week: 2 },
              ],
              edges: [
                { parent: "t1", child: "m1", kind: "covers", origin: "milestone_covers", confidence: 1 },
                ...created.map((e) => ({ ...e, kind: "strict", origin: "user", confidence: 1 })),
              ],
            }),
            { status: 200 },
          );
        }
        if (url.endsWith("/roadmaps/rm-m/graph/layout")) {
          return new Response(JSON.stringify({ positions: [], saved: 0 }), { status: 200 });
        }
        if (url.endsWith("/roadmaps/rm-m/graph/edges") && init?.method === "POST") {
          const body = JSON.parse(String(init.body));
          created.push({ parent_id: body.parent_id, child_id: body.child_id });
          return new Response(
            JSON.stringify({ ...body, origin: "user", confidence: 1 }),
            { status: 201 },
          );
        }
        return new Response(JSON.stringify([]), { status: 200 });
      }),
    );

    render(<CoreJourney page="Roadmap" go={vi.fn()} />);
    const parentSelect = await screen.findByLabelText("Học trước");
    const childSelect = screen.getByLabelText("Học sau");

    await waitFor(() => {
      expect(parentSelect.textContent).toContain("Midterm Quiz · Mốc kiểm tra");
      expect(parentSelect.textContent).toContain("Topic One · Chủ đề");
    });

    // Self-edge disables submit and warns clearly.
    fireEvent.change(parentSelect, { target: { value: "m1" } });
    fireEvent.change(childSelect, { target: { value: "m1" } });
    expect(
      (screen.getByRole("button", { name: "Thêm cạnh" }) as HTMLButtonElement)
        .disabled,
    ).toBe(true);
    expect(screen.getByRole("alert").textContent).toContain("chính nó");

    // Cycle through milestone covers (m1 -> t1 when t1 -> m1 covers exists) is blocked before API call.
    fireEvent.change(parentSelect, { target: { value: "m1" } });
    fireEvent.change(childSelect, { target: { value: "t1" } });
    fireEvent.click(screen.getByRole("button", { name: "Thêm cạnh" }));
    expect(screen.getByRole("alert").textContent).toContain("vòng lặp");
    expect(created).toHaveLength(0);

    // Valid milestone edge (m1 -> t2) succeeds and persists via API.
    fireEvent.change(parentSelect, { target: { value: "m1" } });
    fireEvent.change(childSelect, { target: { value: "t2" } });
    fireEvent.click(screen.getByRole("button", { name: "Thêm cạnh" }));
    await waitFor(() => {
      expect(created).toEqual([{ parent_id: "m1", child_id: "t2" }]);
    });
  });
});
