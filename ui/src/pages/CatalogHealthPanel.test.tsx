// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { BackendError } from "../api/backend";
import type { CatalogHealth } from "../api/types";
import { CatalogHealthPanel } from "./CatalogHealthPanel";

afterEach(cleanup);

const health: CatalogHealth = {
  days: 7,
  insufficient_nodes: 3,
  gaps: [{ subject_id: "ct.ladder", name: "Solution ladder", nodes: 2 }],
  resources: { verified: 20, pending: 14 },
  connectors: [
    {
      connector: "mit_ocw",
      runs: 4,
      errors: 1,
      created: 6,
      last_run_at: "2030-01-07T19:00:00Z",
      last_error: "index_timeout",
    },
  ],
  dead_links: 1,
  dead: [
    {
      id: "r1",
      title: "Gone page",
      url: "https://example.edu/gone",
      http_status: 404,
      last_checked_at: "2030-01-07T00:00:00Z",
    },
  ],
  gap_runs: [
    {
      kind: "fill_gaps",
      at: "2030-01-07T19:00:00Z",
      insufficient_before: 5,
      insufficient_after: 3,
      ingest_jobs: 8,
    },
  ],
};

it("shows gaps per subject, failing connectors, dead links and how the gap count moved", async () => {
  render(<CatalogHealthPanel load={async () => health} />);
  expect((await screen.findByRole("row", { name: /Solution ladder/ })).textContent).toContain("2");
  expect(screen.getByRole("row", { name: /mit_ocw/ }).textContent).toContain("index_timeout");
  expect(screen.getByText(/14 pending/)).toBeTruthy();
  expect(screen.getByRole("row", { name: /Nightly gap filling/ }).textContent).toContain("5 → 3");
  expect(screen.getByRole("link", { name: "Gone page" }).getAttribute("href")).toBe(
    "https://example.edu/gone",
  );
});

it("tells a non-admin why nothing is shown", async () => {
  render(
    <CatalogHealthPanel
      load={async () => {
        throw new BackendError(403, "Forbidden");
      }}
    />,
  );
  expect((await screen.findByRole("alert")).textContent).toBe(
    "Only admins can see catalog health.",
  );
});

it("renders cleanly with empty connectors and no dead links", async () => {
  const emptyHealth: CatalogHealth = {
    ...health,
    connectors: [],
    dead: [],
    dead_links: 0,
  };
  render(<CatalogHealthPanel load={async () => emptyHealth} />);
  expect(await screen.findByText("No connector runs in this window.")).toBeTruthy();
  expect(screen.queryByRole("link", { name: "Gone page" })).toBeNull();
});
