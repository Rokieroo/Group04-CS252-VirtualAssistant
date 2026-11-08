import { call } from "./backend";
import type { CatalogHealth, CostReport } from "./types";

/** Spend over the last ``days``; the backend answers 403 unless the user is an admin. */
export const loadCosts = (days = 7) => call<CostReport>(`/admin/costs?days=${days}`);

/** Catalog gaps, connector failures and dead links (#105); admins only, like costs. */
export const loadCatalogHealth = (days = 7) =>
  call<CatalogHealth>(`/admin/catalog/health?days=${days}`);
