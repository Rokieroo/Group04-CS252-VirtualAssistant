import { useEffect, useState } from "react";

/** Every route; the id is the #hash, so old bookmarks keep opening the same page. */
export type Page =
  | "Home"
  | "Library"
  | "Roadmap"
  | "Schedule"
  | "Sources"
  | "Progress"
  | "AI Reporter"
  | "Companion"
  | "Workspace"
  | "Costs"
  | "Catalog";
export const pages: Page[] = [
  "Home",
  "Library",
  "Roadmap",
  "Schedule",
  "Sources",
  "Progress",
  "AI Reporter",
  "Companion",
  "Workspace",
  "Costs",
  "Catalog",
];
// Visible names. "Library" keeps the id it had when it held the course list.
export const pageLabels: Record<Page, string> = {
  Home: "Home",
  Library: "Courses",
  Roadmap: "Roadmap",
  Schedule: "Schedule",
  Sources: "Library",
  Progress: "Mastery",
  "AI Reporter": "Ask",
  Companion: "Companion",
  Workspace: "Workspace",
  Costs: "Costs",
  Catalog: "Catalog",
};
/**
 * The core loop only (spec 1.2): course → roadmap → schedule → saved sources.
 * Supplementary pages (Mastery, Ask, Companion) keep their routes but open from a
 * course or node, never from here. Settings is a dialog, rendered after these.
 */
export const nav: { page: Page; icon: string }[] = [
  { page: "Library", icon: "▣" },
  { page: "Roadmap", icon: "◇" },
  { page: "Schedule", icon: "▤" },
  { page: "Sources", icon: "❒" },
];

export const routeOf = (page: Page) => page.toLowerCase().replaceAll(" ", "-");

/** The page for a #hash, or ``fallback`` when the hash is unknown or not ``allowed``. */
export function pageFromHash(
  hash: string,
  fallback: Page,
  allowed: readonly Page[] = pages,
): Page {
  const route = hash.startsWith("#") ? hash.slice(1) : hash;
  const page = pages.find((p) => routeOf(p) === route);
  return page && allowed.includes(page) ? page : fallback;
}

/**
 * The current page, kept in sync with the #hash; ``go`` sends pages that are not
 * ``allowed`` to ``fallback``. Pass a module-level ``allowed`` so it stays stable.
 */
export function useHashPage(fallback: Page, allowed: readonly Page[] = pages) {
  const [page, setPage] = useState(() =>
    pageFromHash(location.hash, fallback, allowed),
  );
  useEffect(() => {
    // A hash that is not a route (the #main skip link) keeps the current page.
    const sync = () =>
      setPage((current) => pageFromHash(location.hash, current, allowed));
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, [allowed]);
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [page]);
  const go = (next: Page) => {
    const target = allowed.includes(next) ? next : fallback;
    setPage(target);
    location.hash = routeOf(target);
  };
  return [page, go] as const;
}
