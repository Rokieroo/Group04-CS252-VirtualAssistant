import { useCallback, useEffect, useState } from "react";

/** Every screen; the id is the #hash, so a link or a reload opens the same screen. */
export const routes = ["course", "roadmap", "schedule", "library", "admin"] as const;
export type Route = (typeof routes)[number];

export const routeLabels: Record<Route, string> = {
  course: "Môn học",
  roadmap: "Lộ trình",
  schedule: "Lịch học",
  library: "Tài liệu",
  admin: "Quản trị",
};

/** The route for a #hash, or ``fallback`` when the hash names no screen (the #main skip link). */
export function routeFromHash(hash: string, fallback: Route = "course"): Route {
  const id = hash.replace(/^#/, "");
  return (routes as readonly string[]).includes(id) ? (id as Route) : fallback;
}

export function useRoute() {
  const [route, setRoute] = useState<Route>(() => routeFromHash(location.hash));
  useEffect(() => {
    const sync = () => setRoute((current) => routeFromHash(location.hash, current));
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, []);
  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: "auto" });
  }, [route]);
  const go = useCallback((next: Route) => {
    setRoute(next);
    if (location.hash !== `#${next}`) location.hash = next;
  }, []);
  return [route, go] as const;
}
