import { call } from "./backend";

export type VerificationCheck = {
  check: string;
  result: "pass" | "fail" | "warn" | "skip" | "review" | string;
  reason: string;
  checked_at: string;
};

export type CatalogReviewItem = {
  id: string;
  title: string;
  url: string;
  domain?: string;
  provider: string;
  license: string | null;
  verification_status: "pending" | "verified" | "rejected" | string;
  checks: VerificationCheck[];
  subject?: string;
};

export type SubjectReviewLabel = {
  resource_id: string;
  title: string;
  subject_id: string;
  confidence: number;
  method: string;
};

export type DecisionOut = {
  id: string;
  verification_status: string;
  license: string | null;
};

/**
 * Fetch resources requiring admin review from GET /admin/catalog/review-queue (issue #101, #104).
 */
export async function fetchCatalogReviewQueue(limit = 100): Promise<CatalogReviewItem[]> {
  const data = await call<{ resources: CatalogReviewItem[] }>(
    `/admin/catalog/review-queue?limit=${limit}`
  );
  return data.resources;
}

/**
 * Approve and verify a catalog resource via POST /admin/catalog/resources/{id}:verify.
 */
export async function verifyCatalogResource(
  id: string,
  reason: string,
  license?: string | null
): Promise<DecisionOut> {
  return await call<DecisionOut>(`/admin/catalog/resources/${encodeURIComponent(id)}:verify`, {
    method: "POST",
    body: JSON.stringify({ reason, license: license || null }),
  });
}

/**
 * Reject a catalog resource via POST /admin/catalog/resources/{id}:reject.
 */
export async function rejectCatalogResource(
  id: string,
  reason: string
): Promise<DecisionOut> {
  return await call<DecisionOut>(`/admin/catalog/resources/${encodeURIComponent(id)}:reject`, {
    method: "POST",
    body: JSON.stringify({ reason }),
  });
}

/**
 * Fetch subject labeling review queue via GET /admin/catalog/subject-review-queue (#99, #104).
 */
export async function fetchSubjectReviewQueue(limit = 100): Promise<SubjectReviewLabel[]> {
  const data = await call<{ labels: SubjectReviewLabel[] }>(
    `/admin/catalog/subject-review-queue?limit=${limit}`
  );
  return data.labels;
}
