import { call } from "./backend";
import type { ExerciseCitation } from "./exercises";

/** How a concept came to be known (#166): asked, inferred from an answer, or said. */
export type Known = "tested" | "inferred" | "learner";

export type PlacementExercise = {
  id: string;
  type: "mcq" | "numeric" | "short" | "proof" | "code";
  prompt: string | null;
  choices: string[];
  location: string;
  citation: ExerciseCitation;
};

export type PlacementAttempt = {
  correct: boolean | null;
  source_answer: string | null;
  location: string;
  citation: ExerciseCitation;
};

export type PlacementState = {
  id: string;
  roadmap_id: string;
  status: "active" | "finished";
  asked: number;
  max_questions: number;
  question: { node_id: string; title: string; exercise: PlacementExercise } | null;
  known: string[];
  unknown: string[];
  skipped: string[];
  total_minutes: number;
  known_minutes: number;
  last_attempt?: PlacementAttempt | null;
};

/** Start a placement test on the roadmap, or resume the open one. */
export function startPlacement(roadmapId: string): Promise<PlacementState> {
  return call(`/roadmaps/${encodeURIComponent(roadmapId)}/placement`, {
    method: "POST",
  });
}

export function answerPlacement(
  placementId: string,
  exerciseId: string,
  response: string,
): Promise<PlacementState> {
  return call(`/placements/${encodeURIComponent(placementId)}/answers`, {
    method: "POST",
    body: JSON.stringify({ exercise_id: exerciseId, response }),
  });
}

/** Mark or unmark a concept; the server keeps prerequisites consistent. */
export function setNodeKnown(
  nodeId: string,
  known: boolean,
): Promise<{ node_id: string; known: Known | null; changed: string[] }> {
  return call(`/roadmap-nodes/${encodeURIComponent(nodeId)}/known`, {
    method: "PUT",
    body: JSON.stringify({ known }),
  });
}
