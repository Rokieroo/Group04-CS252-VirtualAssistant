import { afterEach, describe, expect, it, vi } from "vitest";
import * as backend from "./backend";
import { fetchNodeExercises } from "./exercises";

describe("Exercises API client (Issue #115, #109)", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("fetches node exercises with citations", async () => {
    const mockData = {
      node_id: "node-1",
      count: 2,
      exercises: [
        {
          id: "ex-1",
          type: "mcq",
          prompt: "What is the time complexity of binary search on a sorted array of size n?",
          choices: ["O(1)", "O(log n)", "O(n)", "O(n log n)"],
          citation: {
            source_id: null,
            resource_id: "res-1",
            title: "MIT 6.006 Lecture 1 Notes",
            page: 5,
            url: "https://ocw.mit.edu/6-006",
            institution: "MIT",
            license: "CC-BY-4.0",
          },
        },
      ],
    };

    const callSpy = vi.spyOn(backend, "call").mockResolvedValue(mockData);

    const result = await fetchNodeExercises("node-1", 5);
    expect(callSpy).toHaveBeenCalledWith("/roadmap-nodes/node-1/exercises?limit=5");
    expect(result.count).toBe(2);
    expect(result.exercises[0].citation.institution).toBe("MIT");
  });
});
