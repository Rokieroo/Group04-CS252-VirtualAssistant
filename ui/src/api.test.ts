import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiClient, ApiError } from "./api";

afterEach(() => vi.unstubAllGlobals());

describe("workspace API transport", () => {
  it("sends credentials in the header and serializes JSON without putting tokens in URLs", async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{"id":"task-1"}', { status: 201 }));
    vi.stubGlobal("fetch", fetcher);
    const client = new ApiClient("private-token", () => {}, "http://localhost:8000/");
    expect(await client.request("/api/v1/tasks", "POST", { title: "Algebra" })).toEqual({ id: "task-1" });
    const [url, options] = fetcher.mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/tasks");
    expect(options.headers.Authorization).toBe("Bearer private-token");
    expect(JSON.parse(options.body)).toEqual({ title: "Algebra" });
  });

  it("expires local authentication on a rejected session", async () => {
    const expired = vi.fn();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response('{"detail":"Session expired"}', { status: 401 })));
    await expect(new ApiClient("old-token", expired).request("/api/v1/me")).rejects.toEqual(
      new ApiError(401, "Session expired"),
    );
    expect(expired).toHaveBeenCalledOnce();
  });

  it("surfaces field validation failures and handles empty successful responses", async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(new Response('{"detail":[{"msg":"Deadline must be in the future"}]}', { status: 422 }))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetcher);
    const client = new ApiClient();
    await expect(client.request("/api/v1/tasks", "POST", {})).rejects.toThrow("Deadline must be in the future");
    expect(await client.request("/api/v1/auth/logout", "POST")).toBeUndefined();
  });

  it("reports a disconnected backend without returning fabricated data", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(new ApiClient().request("/api/v1/schedule")).rejects.toThrow("Cannot reach the workspace");
  });
});
