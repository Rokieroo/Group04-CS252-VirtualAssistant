import { describe, expect, it } from "vitest";

// Every non-test module's source, keyed like "./api/courses.ts".
const sources = import.meta.glob(["./**/*.{ts,tsx}", "!./**/*.test.{ts,tsx}"], {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>;

// Relative specifiers in `from "…"`, side-effect `import "…"` and dynamic `import("…")`.
const SPECIFIER = /(?:from|import)\s*\(?\s*["'](\.{1,2}\/[^"']+)["']/g;

function resolve(from: string, specifier: string): string | undefined {
  const parts = from.split("/").slice(0, -1);
  for (const part of specifier.split("/")) {
    if (part === "..") parts.pop();
    else if (part !== ".") parts.push(part);
  }
  const base = parts.join("/");
  return [base, `${base}.ts`, `${base}.tsx`, `${base}/index.ts`].find(
    (path) => path in sources,
  );
}

/** Every module ``entry`` can load, statically or lazily. */
function reachable(entry: string): string[] {
  const seen = new Set([entry]);
  for (const path of seen)
    for (const [, specifier] of sources[path].matchAll(SPECIFIER)) {
      const target = resolve(path, specifier);
      if (target) seen.add(target);
    }
  return [...seen];
}

describe("real backend mode never loads demo code or data (#53)", () => {
  it("the real app reaches no module under src/demo", () => {
    const loaded = reachable("./CoreApp.tsx");
    expect(loaded).toContain("./api/courses.ts");
    expect(loaded.filter((path) => path.startsWith("./demo/"))).toEqual([]);
  });

  it("App imports the demo only lazily, behind the backend switch", () => {
    const app = sources["./App.tsx"];
    expect(app).toContain('lazy(() => import("./demo/DemoApp"))');
    const staticImports = [...app.matchAll(/from\s*["']([^"']+)["']/g)].map((m) => m[1]);
    expect(staticImports.filter((path) => path.includes("demo"))).toEqual([]);
  });

  it("the walk does follow imports (the demo reaches its fixtures)", () => {
    expect(reachable("./demo/DemoApp.tsx")).toContain("./demo/fixtures.ts");
  });
});
