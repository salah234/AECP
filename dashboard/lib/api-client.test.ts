import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApiError,
  approveEscalation,
  createTask,
  listReadyTasks,
  updateTaskStatus,
} from "./api-client";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("listReadyTasks", () => {
  it("returns parsed task list on success", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse([{ taskId: "t-1", title: "Do thing", status: "pending", riskTier: "local" }]),
    );
    vi.stubGlobal("fetch", fetchMock);

    const tasks = await listReadyTasks();

    expect(tasks).toHaveLength(1);
    expect(tasks[0]?.taskId).toBe("t-1");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/tasks"),
      expect.objectContaining({ credentials: "include" }),
    );
  });

  it("throws ApiError with the status and detail on a non-2xx response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(jsonResponse({ detail: "Not authenticated" }, 401)),
    );

    await expect(listReadyTasks()).rejects.toMatchObject({
      name: "ApiError",
      status: 401,
      detail: "Not authenticated",
    });
  });

  it("surfaces a 501 as an ApiError so callers can render a not-available state", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        jsonResponse({ detail: "No RPC exists yet to list pending escalations" }, 501),
      ),
    );

    const error = await listReadyTasks().catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(501);
  });

  it("falls back to statusText when the error body isn't JSON", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response("<html>gateway down</html>", { status: 502, statusText: "Bad Gateway" }),
      ),
    );

    await expect(listReadyTasks()).rejects.toMatchObject({ status: 502, detail: "Bad Gateway" });
  });
});

describe("createTask", () => {
  it("posts snake_case fields matching the gateway's request schema", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ taskId: "t-2", title: "New task", status: "pending", riskTier: "local" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createTask({ title: "New task", riskTier: "local", pathGlobs: ["services/**"] });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body).toEqual({
      title: "New task",
      description: "",
      risk_tier: "local",
      path_globs: ["services/**"],
    });
    expect(init.method).toBe("POST");
  });
});

describe("updateTaskStatus", () => {
  it("posts the new status and reason", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      jsonResponse({ taskId: "t-1", title: "x", status: "in_progress", riskTier: "local" }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await updateTaskStatus("t-1", "in_progress", "started");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/api/v1/tasks/t-1/status");
    expect(JSON.parse(init.body as string)).toEqual({ status: "in_progress", reason: "started" });
  });
});

describe("approveEscalation", () => {
  it("handles a 204 No Content response without throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 204 })));

    await expect(approveEscalation("t-1")).resolves.toBeUndefined();
  });
});
