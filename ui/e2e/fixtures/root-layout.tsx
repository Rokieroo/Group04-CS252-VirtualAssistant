// Isolated component fixture: no backend, enrollment or production persistence.
import React, { useState } from "react";
import { createRoot } from "react-dom/client";
import { RootRoadmap } from "../../src/pages/course-setup/RootRoadmap";
function Fixture() {
  const [counts, setCounts] = useState([3, 4, 5]);
  return (
    <>
      <button onClick={() => setCounts([12, 1, 7])}>
        Change checkpoint counts
      </button>
      <RootRoadmap
        courses={counts.map((count, i) => ({
          id: `course-${i}`,
          title: [
            "Computational Thinking",
            "Database Systems",
            "Academic English",
          ][i],
          nodes: Array.from({ length: count }, (_, j) => ({
            id: `${i}-${j}`,
            title: `Lesson ${j + 1}`,
            description: `Checkpoint ${j + 1} description`,
          })),
        }))}
      />
    </>
  );
}
createRoot(document.getElementById("fixture")!).render(<Fixture />);
