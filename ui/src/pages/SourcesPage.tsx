// Old — retained for legacy demo/reference; not used by the redesigned course journey.
import { Button } from "../components/Button";
import { pageLabels, type Page } from "../navigation";

/** S8 Source library. Empty until saved resources (spec 8.6) exist on the backend. */
export function SourcesPage({ go }: { go: (page: Page) => void }) {
  return (
    <section className="card empty" aria-labelledby="sources-empty">
      <h3 id="sources-empty">No saved sources yet</h3>
      <p>
        Sources you keep from a roadmap step appear here, grouped by course,
        with your notes and what you have studied.
      </p>
      <Button onClick={() => go("Roadmap")}>Open {pageLabels.Roadmap}</Button>
    </section>
  );
}
