/** The real backend (src/assistant/backend) for sign-in and course materials.
 * On when VITE_BACKEND_MODE=api; otherwise the demo mocks run with no server. */
export const backendEnabled = import.meta.env.VITE_BACKEND_MODE === "api";

export const API_ORIGIN = String(import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);
const BASE = API_ORIGIN + "/api/v1";
const SESSION = "pathly.session"; // shared with Workspace, so one sign-in serves both

export const session = {
  get(): string {
    try {
      return sessionStorage.getItem(SESSION) || "";
    } catch {
      return "";
    }
  },
  set(token: string) {
    try {
      sessionStorage.setItem(SESSION, token);
    } catch {
      /* memory-only session */
    }
  },
  clear() {
    try {
      sessionStorage.removeItem(SESSION);
    } catch {
      /* memory-only session */
    }
  },
};

/** `code` is the backend's `detail`, e.g. "not_pdf" or "concepts_unavailable". */
export class BackendError extends Error {
  constructor(
    public status: number,
    public code: string,
  ) {
    super(
      status === 0
        ? "Cannot reach the server. Start the backend and check your connection."
        : status === 401
          ? "Your session has ended. Please sign in again."
          : code,
    );
  }
}

/** FastAPI's `detail`: a code string, or a 422's list of validation messages. */
export async function errorDetail(response: Response): Promise<string> {
  const body = await response.json().catch(() => ({}));
  return typeof body.detail === "string"
    ? body.detail
    : Array.isArray(body.detail)
      ? body.detail.map((d: { msg: string }) => d.msg).join("; ")
      : `Request failed (${response.status})`;
}

/** No timeout: concept extraction can take minutes while the AI works. */
export async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = session.get();
  const json = typeof init.body === "string";
  let response: Response;
  try {
    response = await fetch(BASE + path, {
      ...init,
      headers: {
        Accept: "application/json",
        ...(json ? { "Content-Type": "application/json" } : {}),
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      },
    });
  } catch {
    throw new BackendError(0, "unreachable");
  }
  if (!response.ok) {
    const code = await errorDetail(response);
    if (response.status === 401) session.clear();
    throw new BackendError(response.status, code);
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}
