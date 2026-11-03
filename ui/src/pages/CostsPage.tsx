import { useEffect, useState } from "react";
import { BackendError } from "../api/backend";
import { loadCosts } from "../api/costs";
import type { CostReport } from "../api/types";

const WINDOWS = [7, 30, 90];
const usd = (value: number) => `$${value.toFixed(value && value < 0.01 ? 4 : 2)}`;

/** Admin dashboard (issue #69): what resource searches cost, per roadmap step and provider. */
export function CostsPage({ load = loadCosts }: { load?: (days: number) => Promise<CostReport> }) {
  const [days, setDays] = useState(7);
  const [report, setReport] = useState<CostReport | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let current = true;
    setError("");
    load(days).then(
      (value) => current && setReport(value),
      (reason: unknown) =>
        current &&
        setError(
          reason instanceof BackendError && reason.status === 403
            ? "Only admins can see costs."
            : reason instanceof Error
              ? reason.message
              : "Could not load costs.",
        ),
    );
    return () => {
      current = false;
    };
  }, [days, load]);

  if (error) return <p role="alert" className="warning">{error}</p>;
  if (!report) return <p aria-busy="true">Loading costs…</p>;
  const { totals } = report;
  return (
    <div className="costs">
      <label>
        Window{" "}
        <select value={days} onChange={(event) => setDays(Number(event.target.value))}>
          {WINDOWS.map((value) => (
            <option key={value} value={value}>
              Last {value} days
            </option>
          ))}
        </select>
      </label>

      <section className="card stats" aria-label="Totals">
        <div>
          <strong>{usd(totals.cost_usd)}</strong>
          <p>Total · LLM {usd(totals.llm_cost_usd)} · search {usd(totals.search_cost_usd)}</p>
        </div>
        <div>
          <strong>{usd(totals.cost_per_search_usd)}</strong>
          <p>Per search · {totals.searches} searches, {totals.cache_hits} from cache</p>
        </div>
        <div>
          <strong>{totals.llm_calls_today}</strong>
          <p>LLM calls today · {totals.llm_calls} in the window</p>
        </div>
      </section>

      <section className="card">
        <h3>Cost per roadmap step</h3>
        {report.nodes.length === 0 ? (
          <p>No resource searches in this window.</p>
        ) : (
          <table className="cost-table">
            <thead>
              <tr>
                <th scope="col">Step</th>
                <th scope="col">Searches</th>
                <th scope="col">From cache</th>
                <th scope="col">LLM calls</th>
                <th scope="col">Cost</th>
              </tr>
            </thead>
            <tbody>
              {report.nodes.map((node) => (
                <tr key={`${node.node_id}:${node.node_title}`}>
                  <th scope="row">{node.node_title}</th>
                  <td>{node.searches}</td>
                  <td>{node.cache_hits}</td>
                  <td>{node.llm_calls}</td>
                  <td>{usd(node.cost_usd)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card">
        <h3>Search providers</h3>
        <table className="cost-table">
          <thead>
            <tr>
              <th scope="col">Provider</th>
              <th scope="col">Calls</th>
              <th scope="col">Today</th>
              <th scope="col">Errors</th>
              <th scope="col">Avg latency</th>
              <th scope="col">Max latency</th>
              <th scope="col">Cost</th>
            </tr>
          </thead>
          <tbody>
            {report.providers.map((provider) => (
              <tr key={provider.provider}>
                <th scope="row">{provider.provider}</th>
                <td>{provider.calls}</td>
                <td>{provider.calls_today}</td>
                <td>{provider.errors}</td>
                <td>{Math.round(provider.avg_latency_ms)} ms</td>
                <td>{provider.max_latency_ms} ms</td>
                <td>{usd(provider.cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h3>Per day</h3>
        <table className="cost-table">
          <thead>
            <tr>
              <th scope="col">Day</th>
              <th scope="col">Searches</th>
              <th scope="col">Cost</th>
            </tr>
          </thead>
          <tbody>
            {report.daily.map((day) => (
              <tr key={day.day}>
                <th scope="row">{day.day}</th>
                <td>{day.searches}</td>
                <td>{usd(day.cost_usd)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
