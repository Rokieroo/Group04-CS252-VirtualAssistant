import { defineConfig } from "vite";

// e2e starts several dev servers with different env; sharing one optimizer cache makes each
// invalidate the others' and reload pages mid-test, so each server can name its own.
export default defineConfig({ cacheDir: process.env.VITE_CACHE_DIR || "node_modules/.vite" });
