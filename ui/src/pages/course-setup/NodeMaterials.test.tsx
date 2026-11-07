// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NodeMaterials } from "./NodeMaterials";
import * as materialsApi from "../../api/materials";
import * as resourcesApi from "../../api/resources";

describe("S6 NodeMaterials Component (Issue #58, Spec 8.6, 8.7)", () => {
  beforeEach(() => {
    vi.spyOn(materialsApi, "nodeMaterials").mockResolvedValue([]);
    vi.spyOn(materialsApi, "nodeSources").mockResolvedValue({
      node_id: "node-1",
      status: "ready",
      user_material_count: 0,
      sources: [],
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("displays exact spec text 'Chưa tìm được nguồn đủ tốt' when status is insufficient", async () => {
    vi.spyOn(resourcesApi, "fetchNodeResources").mockResolvedValue({
      status: "insufficient",
      resources: [],
      gaps: ["No sources scored above 0.65 threshold"],
    });

    render(<NodeMaterials nodeId="node-1" />);

    expect(await screen.findByText("Chưa tìm được nguồn đủ tốt")).toBeTruthy();
    expect(screen.getByText(/ngưỡng chất lượng thẩm định ≥ 0.65/)).toBeTruthy();
    expect(screen.getAllByRole("button", { name: /Tìm lại/ }).length).toBe(2);
  });

  it("renders verified catalog resource with real domain and safe external link", async () => {
    vi.spyOn(resourcesApi, "fetchNodeResources").mockResolvedValue({
      status: "ready",
      resources: [
        {
          id: "r101",
          rank: 1,
          title: "Introduction to Algorithms - MIT OCW",
          url: "https://ocw.mit.edu/courses/6-006",
          domain: "ocw.mit.edu",
          format: "video",
          language: "en",
          duration_min: 45,
          is_free: true,
          score: 0.91,
          breakdown: { relevance: 0.95, authority: 1.0 },
          reason: "Matches CLO 1.2 decomposition",
          evidence_quote: "Algorithms break complex processes into steps",
          pinned: false,
        },
      ],
      gaps: [],
    });

    render(<NodeMaterials nodeId="node-1" />);

    const link = await screen.findByRole("link", {
      name: /Introduction to Algorithms - MIT OCW/i,
    });
    expect(link).toBeTruthy();
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
    expect(screen.getByText("ocw.mit.edu")).toBeTruthy();
    expect(screen.getByText("✓ Đã xác minh")).toBeTruthy();
    expect(screen.getByText(/★ 91%/)).toBeTruthy();
  });

  it("filters resources by format when format tabs are clicked", async () => {
    vi.spyOn(resourcesApi, "fetchNodeResources").mockResolvedValue({
      status: "ready",
      resources: [
        {
          id: "r1",
          rank: 1,
          title: "Video Lecture 1",
          url: "https://youtube.com/v1",
          domain: "youtube.com",
          format: "video",
          language: "en",
          duration_min: 20,
          is_free: true,
          score: 0.85,
          breakdown: {},
          reason: "",
          evidence_quote: "",
          pinned: false,
        },
        {
          id: "r2",
          rank: 2,
          title: "Article Reading 1",
          url: "https://mit.edu/a1",
          domain: "mit.edu",
          format: "article",
          language: "en",
          duration_min: 15,
          is_free: true,
          score: 0.80,
          breakdown: {},
          reason: "",
          evidence_quote: "",
          pinned: false,
        },
      ],
      gaps: [],
    });

    render(<NodeMaterials nodeId="node-1" />);

    await screen.findByText(/Video Lecture 1/);
    expect(screen.getByText(/Article Reading 1/)).toBeTruthy();

    // Click Video filter
    fireEvent.click(screen.getByRole("button", { name: /Video/ }));
    expect(screen.getByText(/Video Lecture 1/)).toBeTruthy();
    expect(screen.queryByText(/Article Reading 1/)).toBeNull();

    // Click Article filter
    fireEvent.click(screen.getByRole("button", { name: "Bài viết / Đọc" }));
    expect(screen.queryByText(/Video Lecture 1/)).toBeNull();
    expect(screen.getByText(/Article Reading 1/)).toBeTruthy();
  });

  it("handles one-tap feedback and replaces unhelpful resource in-place", async () => {
    const feedbackSpy = vi.spyOn(resourcesApi, "sendResourceFeedback").mockResolvedValue({
      status: "ok",
      replacement: {
        id: "r_replacement",
        rank: 1,
        title: "Replacement Resource from Stanford",
        url: "https://stanford.edu/cs106",
        domain: "stanford.edu",
        format: "video",
        language: "en",
        duration_min: 30,
        is_free: true,
        score: 0.87,
        breakdown: {},
        reason: "Higher relevance alternative",
        evidence_quote: "Stanford alternative quote",
        pinned: false,
      },
    });

    vi.spyOn(resourcesApi, "fetchNodeResources").mockResolvedValue({
      status: "ready",
      resources: [
        {
          id: "r1",
          rank: 1,
          title: "Old Resource to Reject",
          url: "https://bad.org/1",
          domain: "bad.org",
          format: "video",
          language: "en",
          duration_min: 10,
          is_free: true,
          score: 0.70,
          breakdown: {},
          reason: "Initial candidate",
          evidence_quote: "",
          pinned: false,
        },
      ],
      gaps: [],
    });

    render(<NodeMaterials nodeId="node-1" />);

    await screen.findByText(/Old Resource to Reject/);

    // Tap thumbs down
    fireEvent.click(screen.getByRole("button", { name: /Không phù hợp/ }));

    await waitFor(() => {
      expect(feedbackSpy).toHaveBeenCalledWith("r1", {
        node_id: "node-1",
        helpful: false,
        reason: "wrong_level",
      });
    });

    // In-place replacement
    expect(await screen.findByText(/Replacement Resource from Stanford/)).toBeTruthy();
    expect(screen.queryByText(/Old Resource to Reject/)).toBeNull();
  });

  it("triggers searchNodeResources when 'Tìm lại' is clicked", async () => {
    const searchSpy = vi.spyOn(resourcesApi, "searchNodeResources").mockResolvedValue({
      run_id: "run-abc",
    });

    vi.spyOn(resourcesApi, "fetchNodeResources").mockResolvedValue({
      status: "ready",
      resources: [],
      gaps: [],
    });

    render(<NodeMaterials nodeId="node-1" />);

    const searchBtns = await screen.findAllByRole("button", { name: /Tìm lại/ });
    fireEvent.click(searchBtns[0]);

    expect(searchSpy).toHaveBeenCalledWith("node-1");
  });
});
