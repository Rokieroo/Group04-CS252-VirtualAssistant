import { call } from "./backend";
import type { CostReport } from "./types";

/** Spend over the last ``days``; the backend answers 403 unless the user is an admin. */
export const loadCosts = (days = 7) => call<CostReport>(`/admin/costs?days=${days}`);
