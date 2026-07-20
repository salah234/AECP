import { afterEach, describe, expect, it, vi } from "vitest";

import { getCurrentUser } from "./auth";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("getCurrentUser", () => {
  it("returns the user on a successful response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ subject: "em-1", tenantId: "tenant-a", role: "em" }), {
          status: 200,
        }),
      ),
    );

    const user = await getCurrentUser();

    expect(user).toEqual({ subject: "em-1", tenantId: "tenant-a", role: "em" });
  });

  it("returns null on 401 rather than throwing", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 401 })));

    await expect(getCurrentUser()).resolves.toBeNull();
  });

  it("throws on an unexpected error status", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(null, { status: 500 })));

    await expect(getCurrentUser()).rejects.toThrow(/500/);
  });
});
