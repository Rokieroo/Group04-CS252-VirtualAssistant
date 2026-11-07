import { call } from "./backend";

export type ExerciseCitation = {
  source_id: string | null;
  resource_id: string | null;
  title: string;
  page: number | null;
  url: string | null;
  institution: string | null;
  license: string;
};

export type ExerciseItem = {
  id: string;
  type: "mcq" | "numeric" | "short" | "proof" | "code";
  prompt: string;
  choices: string[];
  citation: ExerciseCitation;
};

export type NodeExercisesOut = {
  node_id: string;
  count: number;
  exercises: ExerciseItem[];
};

/**
 * Fetch exercises with citations for a roadmap node (issue #115, #109).
 */
export async function fetchNodeExercises(
  nodeId: string,
  limit = 10,
): Promise<NodeExercisesOut> {
  return await call<NodeExercisesOut>(
    `/roadmap-nodes/${encodeURIComponent(nodeId)}/exercises?limit=${limit}`,
  );
}
