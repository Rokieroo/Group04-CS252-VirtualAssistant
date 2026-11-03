import { Button } from "../../components/Button";
import { courses } from "../fixtures";
import type { State } from "../domain";
import { pageLabels } from "../../navigation";

type Props = {
  state: State;
  query: string;
  setQuery: (value: string) => void;
  filter: string;
  setFilter: (value: string) => void;
  futureTab: boolean;
  setFutureTab: (value: boolean) => void;
  requestCourse: (id: string) => void;
};
export function LibraryPage({
  state,
  query,
  setQuery,
  filter,
  setFilter,
  futureTab,
  setFutureTab,
  requestCourse,
}: Props) {
  const displayCourses = courses.filter(
    (c) =>
      (!futureTab || state.future.includes(c.id)) &&
      (filter === "All modules" || filter === c.category) &&
      `${c.name} ${c.description}`.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <>
      <input
        className="search"
        aria-label="Search modules"
        placeholder="⌕  Search subjects, courses, or skill levels..."
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="filters" aria-label={`${pageLabels.Library} filters`}>
        {[
          "All modules",
          "Mathematics",
          "Languages",
          "Sciences",
          "Humanities",
          "Technology",
        ].map((f) => (
          <button
            aria-pressed={filter === f}
            className={filter === f ? "selected" : ""}
            key={f}
            onClick={() => setFilter(f)}
          >
            {f}
          </button>
        ))}
      </div>
      <div className="toolbar">
        <h2>{futureTab ? "Future learning plan" : "Recommended for you"}</h2>
        <div className="spacer" />
        <button
          className={!futureTab ? "text-button selected" : "text-button"}
          onClick={() => setFutureTab(false)}
        >
          Built-in study paths
        </button>
        <button
          className={futureTab ? "text-button selected" : "text-button"}
          onClick={() => setFutureTab(true)}
        >
          Saved for later ({state.future.length})
        </button>
      </div>
      <div className="two-columns course-grid">
        {displayCourses.map((c, i) => (
          <article className="card course" key={c.id}>
            <div className="course-heading">
              <span className={`number ${c.color}`}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <div>
                <h3>{c.name}</h3>
                <p>{c.description}</p>
              </div>
            </div>
            <p>Prerequisite: {c.prerequisite}</p>
            <div className="course-footer">
              <span className={`pill ${c.color}`}>{c.weeks} weeks</span>
              <span className="pill neutral">{c.level}</span>
              <Button primary onClick={() => requestCourse(c.id)}>
                {state.active.includes(c.id)
                  ? "View enrollment"
                  : "Choose module →"}
              </Button>
            </div>
            {futureTab && (
              <p className="amber-text">Saved · Not enrolled or scheduled</p>
            )}
          </article>
        ))}
      </div>
      {displayCourses.length === 0 && (
        <div className="card empty">
          <h3>
            {futureTab
              ? "No saved modules yet"
              : "No modules match your search"}
          </h3>
          <p>
            {futureTab
              ? `Choose a module and select “Add to future plan” in ${pageLabels["AI Reporter"]}.`
              : "Try another subject or clear the filters."}
          </p>
          <Button
            onClick={() => {
              setQuery("");
              setFilter("All modules");
              setFutureTab(false);
            }}
          >
            Browse all modules
          </Button>
        </div>
      )}
      <div className="card footnote">
        ✦ Selecting a module opens {pageLabels["AI Reporter"]} for a
        prerequisite check. Enrollment is confirmed before lessons appear in{" "}
        {pageLabels.Schedule}.
      </div>
    </>
  );
}
