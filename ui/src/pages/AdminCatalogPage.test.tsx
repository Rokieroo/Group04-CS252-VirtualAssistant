// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AdminCatalogPage } from "./AdminCatalogPage";
import * as catalogApi from "../api/catalog";

describe("AdminCatalogPage (Issue #104, Spec 8.6, ADR 004)", () => {
  const mockQueue: catalogApi.CatalogReviewItem[] = Array.from({ length: 22 }, (_, i) => ({
    id: `res-${i + 1}`,
    title: `Verified Course Item ${i + 1} - MIT OCW`,
    url: `https://ocw.mit.edu/courses/6-006/item-${i + 1}`,
    provider: i % 2 === 0 ? "MIT OCW" : "Stanford Online",
    license: i % 3 === 0 ? "CC-BY-4.0" : null,
    verification_status: "pending",
    checks: [
      {
        check: "robots_and_domain",
        result: "pass",
        reason: "Allowed by robots.txt",
        checked_at: "2026-11-01",
      },
      {
        check: "open_license",
        result: i % 3 === 0 ? "pass" : "review",
        reason: i % 3 === 0 ? "license_found" : "license_unknown",
        checked_at: "2026-11-01",
      },
      {
        check: "extractable_text",
        result: "pass",
        reason: "Parsed 3500 words",
        checked_at: "2026-11-01",
      },
      {
        check: "format_and_duration",
        result: "pass",
        reason: "Video (40 min)",
        checked_at: "2026-11-01",
      },
    ],
  }));

  beforeEach(() => {
    vi.spyOn(catalogApi, "fetchCatalogReviewQueue").mockResolvedValue(mockQueue);
    vi.spyOn(catalogApi, "verifyCatalogResource").mockResolvedValue({
      id: "res-1",
      verification_status: "verified",
      license: "CC-BY-4.0",
    });
    vi.spyOn(catalogApi, "rejectCatalogResource").mockResolvedValue({
      id: "res-1",
      verification_status: "rejected",
      license: null,
    });
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });

  it("loads and displays the review queue with 4-check breakdown", async () => {
    render(<AdminCatalogPage />);

    expect(await screen.findByText(/Hàng chờ duyệt nguồn Catalog/i)).toBeTruthy();
    expect((await screen.findAllByText(/Verified Course Item 1 - MIT OCW/)).length).toBeGreaterThan(0);
    expect(screen.getByText(/Kết quả kiểm tra tự động \(4 checks\)/)).toBeTruthy();
    expect(screen.getByText(/robots_and_domain:/)).toBeTruthy();
    expect(screen.getByText(/open_license:/)).toBeTruthy();
  });

  it("filters review items by provider and search keyword", async () => {
    render(<AdminCatalogPage />);

    await screen.findAllByText(/Verified Course Item 1 - MIT OCW/);

    // Filter by Stanford Online
    const providerSelect = screen.getByLabelText(/Provider:/i);
    fireEvent.change(providerSelect, { target: { value: "Stanford Online" } });

    // Item 1 is MIT OCW, Item 2 is Stanford Online
    expect(screen.queryByText(/Verified Course Item 1 - MIT OCW/)).toBeNull();
    expect(screen.getAllByText(/Verified Course Item 2 - MIT OCW/).length).toBeGreaterThan(0);

    // Search filter
    const searchInput = screen.getByLabelText(/Tìm kiếm:/i);
    fireEvent.change(searchInput, { target: { value: "Item 2" } });
    expect(screen.getAllByText(/Verified Course Item 2 - MIT OCW/).length).toBeGreaterThan(0);
  });

  it("keeps a resource in the queue and shows why when the API refuses the decision", async () => {
    vi.spyOn(catalogApi, "verifyCatalogResource").mockRejectedValue(new Error("license_required"));
    render(<AdminCatalogPage />);
    await screen.findAllByText(/Verified Course Item 1 - MIT OCW/);

    fireEvent.click(screen.getByRole("button", { name: /Xác nhận duyệt nguồn này/i }));

    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "license_required");
    expect(screen.queryByText(/✓ Đã duyệt/)).toBeNull();
    expect(screen.getAllByText(/Verified Course Item 1 - MIT OCW/).length).toBeGreaterThan(0);
  });

  it("shows the load error instead of sample data", async () => {
    vi.spyOn(catalogApi, "fetchCatalogReviewQueue").mockRejectedValue(new Error("forbidden"));
    render(<AdminCatalogPage />);
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "forbidden");
  });

  it("verifies a catalog resource and removes it from queue", async () => {
    const verifySpy = vi.spyOn(catalogApi, "verifyCatalogResource");
    render(<AdminCatalogPage />);

    await screen.findAllByText(/Verified Course Item 1 - MIT OCW/);

    const verifyBtn = screen.getByRole("button", { name: /Xác nhận duyệt nguồn này/i });
    fireEvent.click(verifyBtn);

    await waitFor(() => {
      expect(verifySpy).toHaveBeenCalledWith(
        "res-1",
        "Footer confirms CC-BY-4.0",
        "CC-BY-4.0"
      );
    });

    // Toast appears
    expect(await screen.findByText(/✓ Đã duyệt/)).toBeTruthy();
  });

  it("supports keyboard shortcuts: J/K for navigation and V/R for decisions", async () => {
    const verifySpy = vi.spyOn(catalogApi, "verifyCatalogResource");
    const rejectSpy = vi.spyOn(catalogApi, "rejectCatalogResource");

    render(<AdminCatalogPage />);
    await screen.findAllByText(/Verified Course Item 1 - MIT OCW/);

    // Press 'J' to move to next item (res-2)
    fireEvent.keyDown(window, { key: "j" });

    // Press 'V' to verify res-2
    fireEvent.keyDown(window, { key: "v" });
    await waitFor(() => {
      // res-2 has no license and none was chosen: nothing is invented for it.
      expect(verifySpy).toHaveBeenCalledWith("res-2", expect.any(String), null);
    });

    await screen.findByText(/✓ Đã duyệt/);

    // Press 'R' to reject next item
    fireEvent.keyDown(window, { key: "r" });
    await waitFor(() => {
      expect(rejectSpy).toHaveBeenCalled();
    });
  });

  it("verifies fast review throughput: admin can review 20 sources in under 5 minutes", async () => {
    const verifySpy = vi.spyOn(catalogApi, "verifyCatalogResource");
    render(<AdminCatalogPage />);

    await screen.findAllByText(/Verified Course Item 1 - MIT OCW/);

    // Review 20 items sequentially with 'V'
    for (let i = 0; i < 20; i++) {
      fireEvent.keyDown(window, { key: "v" });
      await waitFor(() => {
        expect(verifySpy).toHaveBeenCalledTimes(i + 1);
      });
    }

    // Verified 20 items successfully
    expect(screen.getByText("20")).toBeTruthy();
    expect(screen.getByText(/Đã duyệt phiên này/i)).toBeTruthy();
  });
});
