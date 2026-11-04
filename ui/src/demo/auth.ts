// Old — retained for legacy demo/reference; not used by the redesigned course journey.
import { assertValid, type Authenticate } from "../api/account";

const delay = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Any valid form signs in; the token lives in memory only, so a reload signs out. */
export const demoAuthenticate: Authenticate = async (form, mode) => {
  assertValid(form, mode);
  await delay(400);
  return { token: `mock-${mode}-${Date.now()}` };
};
