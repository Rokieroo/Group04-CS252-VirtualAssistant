import { beforeEach, describe, expect, it, vi } from "vitest";
import * as backend from "./backend";
import {
  fetchCatalogReviewQueue,
  fetchSubjectReviewQueue,
  rejectCatalogResource,
  verifyCatalogResource,
} from "./catalog";

describe("Catalog Admin API client (Issue #104)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches catalog review queue", async () => {
    const mockData = {
      resources: [
        {
          id: "res-1",
          title: "MIT OCW 6.006 Lecture 1",
          url: "https://ocw.mit.edu/courses/6-006",
          provider: "MIT OCW",
          license: "CC-BY-NC-SA-4.0",
          verification_status: "pending",
          checks: [
            {
              check: "open_license",
              result: "review",
              reason: "license_unknown",
              checked_at: "2026-11-01T00:00:00Z",
            },
          ],
        },
      ],
    };
    const callSpy = vi.spyOn(backend, "call").mockResolvedValue(mockData);

    const result = await fetchCatalogReviewQueue(50);
    expect(callSpy).toHaveBeenCalledWith("/admin/catalog/review-queue?limit=50");
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("res-1");
  });

  it("verifies a catalog resource with reason and license", async () => {
    const mockDecision = {
      id: "res-1",
      verification_status: "verified",
      license: "CC-BY-4.0",
    };
    const callSpy = vi.spyOn(backend, "call").mockResolvedValue(mockDecision);

    const result = await verifyCatalogResource("res-1", "Footer says CC BY 4.0", "CC-BY-4.0");
    expect(callSpy).toHaveBeenCalledWith("/admin/catalog/resources/res-1:verify", {
      method: "POST",
      body: JSON.stringify({ reason: "Footer says CC BY 4.0", license: "CC-BY-4.0" }),
    });
    expect(result.verification_status).toBe("verified");
  });

  it("rejects a catalog resource with reason", async () => {
    const mockDecision = {
      id: "res-2",
      verification_status: "rejected",
      license: null,
    };
    const callSpy = vi.spyOn(backend, "call").mockResolvedValue(mockDecision);

    const result = await rejectCatalogResource("res-2", "takedown requested");
    expect(callSpy).toHaveBeenCalledWith("/admin/catalog/resources/res-2:reject", {
      method: "POST",
      body: JSON.stringify({ reason: "takedown requested" }),
    });
    expect(result.verification_status).toBe("rejected");
  });

  it("fetches subject review queue", async () => {
    const mockData = {
      labels: [
        {
          resource_id: "res-1",
          title: "MIT OCW 6.006",
          subject_id: "algorithms",
          confidence: 0.55,
          method: "keyword",
        },
      ],
    };
    const callSpy = vi.spyOn(backend, "call").mockResolvedValue(mockData);

    const result = await fetchSubjectReviewQueue(20);
    expect(callSpy).toHaveBeenCalledWith("/admin/catalog/subject-review-queue?limit=20");
    expect(result[0].subject_id).toBe("algorithms");
  });
});
