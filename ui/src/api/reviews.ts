import { call } from "./backend";

export type DueReviewCard = {
  item_id: string;
  user_id: string;
  node_id?: string | null;
  due_at: string;
  stability: number;
  difficulty: number;
  state: number;
  step: number;
  last_review?: string | null;
  prompt: string;
  choices?: string[] | null;
  type: string;
  source_id?: string | null;
};

export type ReviewSubmitResult = {
  item_id: string;
  user_id: string;
  node_id?: string | null;
  rating: number;
  due_at: string;
  stability: number;
  difficulty: number;
  state: number;
  step: number;
  last_review: string;
  elapsed_days: number;
  scheduled_days: number;
  retrievability: number;
};

export async function fetchDueReviews(limit = 50): Promise<DueReviewCard[]> {
  return call<DueReviewCard[]>(`/reviews/due?limit=${limit}`);
}

export async function submitReview(
  itemId: string,
  rating: number,
  nodeId?: string,
): Promise<ReviewSubmitResult> {
  return call<ReviewSubmitResult>(`/reviews/${encodeURIComponent(itemId)}`, {
    method: "POST",
    body: JSON.stringify({ rating, node_id: nodeId }),
  });
}
