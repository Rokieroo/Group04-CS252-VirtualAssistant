// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it, vi } from "vitest";
import { BackendError } from "../api/backend";
import type { CostReport } from "../api/types";
import { CostsPage } from "./CostsPage";

afterEach(cleanup);

const report: CostReport = {
  days: 7,
  since: "2030-01-01T00:00:00Z",
  totals: {
    searches: 2,
    cache_hits: 1,
    llm_calls: 3,
    llm_calls_today: 3,
    llm_cost_usd: 0.03,
    search_cost_usd: 0.005,
    cost_usd: 0.035,
    cost_per_search_usd: 0.0175,
  },
  nodes: [
    {
      node_id: "n1",
      node_title: "Recursion",
      searches: 2,
      cache_hits: 1,
      llm_calls: 3,
      llm_cost_usd: 0.03,
      search_cost_usd: 0.005,
      cost_usd: 0.035,
      last_search_at: "2030-01-07T00:00:00Z",
    },
  ],
  providers: [
    {
      provider: "web",
      calls: 5,
      errors: 0,
      calls_today: 5,
      avg_latency_ms: 412.4,
      max_latency_ms: 900,
      cost_usd: 0.005,
    },
  ],
  daily: [{ day: "2030-01-07", searches: 2, cost_usd: 0.035 }],
};

it("shows the cost of every roadmap step and each provider's latency", async () => {
  render(<CostsPage load={async () => report} />);
  const step = await screen.findByRole("row", { name: /Recursion/ });
  expect(step.textContent).toContain("$0.04");
  expect(screen.getByRole("row", { name: /web/ }).textContent).toContain("412 ms");
  expect(screen.getByText(/2 searches, 1 from cache/)).toBeTruthy();
});

it("reloads for another window", async () => {
  const load = vi.fn(async () => report);
  render(<CostsPage load={load} />);
  await userEvent.selectOptions(await screen.findByRole("combobox"), "30");
  expect(load).toHaveBeenLastCalledWith(30);
});

it("tells non-admins the page is for admins", async () => {
  render(<CostsPage load={() => Promise.reject(new BackendError(403, "admin_only"))} />);
  expect((await screen.findByRole("alert")).textContent).toBe("Only admins can see costs.");
});
