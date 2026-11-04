// Old — retained for legacy demo/reference; not used by the redesigned course journey.
import { Button } from "../components/Button";
import { pageLabels, type Page } from "../navigation";

/** S5 Roadmap. Empty until the roadmap screen (#57) reads /roadmaps from the backend. */
export function RoadmapPage({ go }: { go: (page: Page) => void }) {
  return (
    <section className="card empty" aria-labelledby="roadmap-empty">
      <h3 id="roadmap-empty">No roadmap yet</h3>
      <p>
        A roadmap is built from a confirmed syllabus: weekly steps, exam
        milestones, and study sessions placed on your calendar.
      </p>
      <Button primary onClick={() => go("Library")}>
        Open {pageLabels.Library}
      </Button>
    </section>
  );
}
