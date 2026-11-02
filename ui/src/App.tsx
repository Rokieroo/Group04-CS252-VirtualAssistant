import { lazy, Suspense } from "react";
import { backendEnabled } from "./api/backend";
import CoreApp from "./CoreApp";

// Its own chunk, fetched only without a backend: the real app never loads demo code or data.
const DemoApp = lazy(() => import("./demo/DemoApp"));

/** VITE_BACKEND_MODE=api runs the real app; anything else, the offline demo. */
export default function App() {
  return backendEnabled ? (
    <CoreApp />
  ) : (
    <Suspense fallback={null}>
      <DemoApp />
    </Suspense>
  );
}
