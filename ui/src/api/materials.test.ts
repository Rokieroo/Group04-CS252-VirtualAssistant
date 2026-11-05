import { afterEach, describe, expect, it, vi } from "vitest";
import { decideMaterial, nodeMaterials, pageRanges, type MaterialFile } from "./materials";

const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});
afterEach(() => vi.unstubAllGlobals());

describe("#114 the learner's own material on a node", () => {
  it("reads consecutive pages as ranges", () => {
    expect(pageRanges([7, 2, 3, 3, 4, 9])).toBe("2–4, 7, 9");
    expect(pageRanges([])).toBe("");
  });

  it("confirms every page of a suggestion with one tap", async () => {
    const fetch = vi.fn().mockResolvedValue(reply({}));
    vi.stubGlobal("fetch", fetch);
    const file: MaterialFile = {
      file_name: "week1.pptx",
      status: "suggested",
      pages: [
        { source_id: "s 2", page: 2, confidence: 0.4, method: "auto" },
        { source_id: "s3", page: 3, confidence: 0.5, method: "auto" },
      ],
    };
    await decideMaterial("n1", file, true);
    expect(fetch.mock.calls.map((c) => [c[0], c[1].method, JSON.parse(c[1].body)])).toEqual([
      [expect.stringMatching(/\/roadmap-nodes\/n1\/materials\/s%202$/), "PUT", { attached: true }],
      [expect.stringMatching(/\/roadmap-nodes\/n1\/materials\/s3$/), "PUT", { attached: true }],
    ]);
  });

  it("lists the node's files", async () => {
    const files = [{ file_name: "a.pdf", status: "attached", pages: [] }];
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply({ node_id: "n1", files })));
    expect(await nodeMaterials("n1")).toEqual(files);
  });
});
