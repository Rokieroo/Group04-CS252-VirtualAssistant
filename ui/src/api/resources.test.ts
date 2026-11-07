import { afterEach, describe, expect, it, vi } from "vitest";
import {
  fetchNodeResources,
  searchNodeResources,
  sendResourceFeedback,
} from "./resources";

const reply = (body: unknown, status = 200) => ({
  ok: status < 400,
  status,
  json: async () => body,
});

afterEach(() => vi.unstubAllGlobals());

describe("resources API (spec 8.5–8.7, issue #58)", () => {
  it("fetches node resources with quality status", async () => {
    const data = {
      status: "ready",
      resources: [
        {
          id: "r1",
          rank: 1,
          title: "MIT OCW Computational Thinking",
          url: "https://ocw.mit.edu/courses/6-0001",
          domain: "ocw.mit.edu",
          format: "article",
          language: "en",
          duration_min: 30,
          is_free: true,
          score: 0.88,
          breakdown: {
            relevance: 0.92,
            authority: 1.0,
            level_fit: 0.85,
            pedagogy: 0.9,
            freshness: 0.8,
            accessibility: 0.95,
            community: 0.8,
          },
          reason: "Covers CLO 1.2 decomposition",
          evidence_quote: "Decomposition involves breaking down problems",
          pinned: false,
        },
      ],
      gaps: [],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(data)));
    const res = await fetchNodeResources("node-123");
    expect(res.status).toBe("ready");
    expect(res.resources[0].domain).toBe("ocw.mit.edu");
    expect(res.resources[0].score).toBe(0.88);
  });

  it("handles insufficient status from backend", async () => {
    const data = {
      status: "insufficient",
      resources: [],
      gaps: ["No verified sources above 0.65 threshold"],
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(reply(data)));
    const res = await fetchNodeResources("node-empty");
    expect(res.status).toBe("insufficient");
    expect(res.resources).toHaveLength(0);
  });

  it("triggers search on node resources", async () => {
    const fetch = vi.fn().mockResolvedValue(reply({ run_id: "run-99" }));
    vi.stubGlobal("fetch", fetch);
    const res = await searchNodeResources("node-123");
    expect(res.run_id).toBe("run-99");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/roadmap-nodes\/node-123\/resources:search$/),
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("sends one-tap feedback and receives replacement", async () => {
    const replacement = {
      id: "r2",
      rank: 1,
      title: "CMU Abstraction Notes",
      url: "https://cs.cmu.edu/notes",
      domain: "cs.cmu.edu",
      format: "article",
      language: "en",
      duration_min: 20,
      is_free: true,
      score: 0.82,
      breakdown: {},
      reason: "Alternative source",
      evidence_quote: "Abstraction extracts essential properties",
      pinned: false,
    };
    const fetch = vi.fn().mockResolvedValue(reply({ status: "ok", replacement }));
    vi.stubGlobal("fetch", fetch);
    const res = await sendResourceFeedback("r1", {
      node_id: "node-123",
      helpful: false,
      reason: "wrong_level",
    });
    expect(res.status).toBe("ok");
    expect(res.replacement?.domain).toBe("cs.cmu.edu");
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/resources\/r1\/feedback$/),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          node_id: "node-123",
          helpful: false,
          reason: "wrong_level",
        }),
      }),
    );
  });
});
