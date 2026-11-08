import { useEffect, useState } from "react";
import { BackendError } from "../api/backend";
import { loadCatalogHealth } from "../api/costs";
import type { CatalogHealth } from "../api/types";

const STATUSES = ["pending", "stale", "rejected"];
const when = (value: string | null) => (value ? new Date(value).toLocaleString() : "—");

/** Admin dashboard (issue #105): where roadmaps lack sources and how the catalog keeps up. */
export function CatalogHealthPanel({
  load = loadCatalogHealth,
}: {
  load?: (days: number) => Promise<CatalogHealth>;
}) {
  const [health, setHealth] = useState<CatalogHealth | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    load(7).then(
      (value) => current && setHealth(value),
      (reason: unknown) =>
        current &&
        setError(
          reason instanceof BackendError && reason.status === 403
            ? "Only admins can see catalog health."
            : reason instanceof Error
              ? reason.message
              : "Could not load catalog health.",
        ),
    );
    return () => {
      current = false;
    };
  }, [load]);

  if (error) return <p role="alert" className="warning">{error}</p>;
  if (!health) return <p aria-busy="true">Loading catalog health…</p>;
  return (
    <div className="costs">
      <section className="card stats" aria-label="Catalog totals">
        <div>
          <strong>{health.insufficient_nodes}</strong>
          <p>Roadmap steps with fewer than 2 sources</p>
        </div>
        <div>
          <strong>{health.resources.verified ?? 0}</strong>
          <p>
            Verified sources ·{" "}
            {STATUSES.map((status) => `${health.resources[status] ?? 0} ${status}`).join(" · ")}
          </p>
        </div>
        <div>
          <strong>{health.dead_links}</strong>
          <p>Dead links</p>
        </div>
      </section>

      <section className="card">
        <h3>Missing sources by subject</h3>
        {health.gaps.length === 0 ? (
          <p>Every roadmap step has enough sources.</p>
        ) : (
          <table className="cost-table">
            <thead>
              <tr>
                <th scope="col">Subject</th>
                <th scope="col">Steps</th>
              </tr>
            </thead>
            <tbody>
              {health.gaps.map((gap) => (
                <tr key={gap.subject_id}>
                  <th scope="row">{gap.name}</th>
                  <td>{gap.nodes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h3>Connectors (last {health.days} days)</h3>
        <table className="cost-table">
          <thead>
            <tr>
              <th scope="col">Connector</th>
              <th scope="col">Runs</th>
              <th scope="col">New sources</th>
              <th scope="col">Errors</th>
              <th scope="col">Last error</th>
              <th scope="col">Last run</th>
            </tr>
          </thead>
          <tbody>
            {health.connectors.map((row) => (
              <tr key={row.connector}>
                <th scope="row">{row.connector}</th>
                <td>{row.runs}</td>
                <td>{row.created}</td>
                <td>{row.errors}</td>
                <td>{row.last_error ?? "—"}</td>
                <td>{when(row.last_run_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>Gap runs</h3>
        <table className="cost-table">
          <thead>
            <tr>
              <th scope="col">When</th>
              <th scope="col">Run</th>
              <th scope="col">Steps short, before → after</th>
              <th scope="col">Ingests queued</th>
            </tr>
          </thead>
          <tbody>
            {health.gap_runs.map((run) => (
              <tr key={`${run.kind}:${run.at}`}>
                <th scope="row">{when(run.at)}</th>
                <td>{run.kind === "fill_gaps" ? "Nightly gap filling" : "Re-match"}</td>
                <td>
                  {run.insufficient_before} → {run.insufficient_after}
                </td>
                <td>{run.ingest_jobs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {health.dead.length > 0 && (
        <section className="card">
          <h3>Dead links</h3>
          <ul>
            {health.dead.map((link) => (
              <li key={link.id}>
                <a href={link.url} target="_blank" rel="noreferrer">
                  {link.title}
                </a>{" "}
                · HTTP {link.http_status ?? "no answer"} · checked {when(link.last_checked_at)}
              </li>
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
