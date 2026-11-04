import { lazy, Suspense } from "react";
import { backendEnabled } from "./api/backend";
import CoreApp from "./CoreApp";

// Old demo is preserved as an explicit opt-in, never the default screen.
const DemoApp = lazy(() => import("./demo/DemoApp"));

/** The redesigned course journey is the default; API mode requires authentication. */
export default function App() {
  return import.meta.env.VITE_BACKEND_MODE !== "legacy-demo" ? (
    <CoreApp mock={!backendEnabled} />
  ) : (
    <Suspense fallback={null}>
      <DemoApp />
    </Suspense>
  );
}
