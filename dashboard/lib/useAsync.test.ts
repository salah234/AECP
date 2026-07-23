import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePolledAsync } from "./useAsync";

describe("usePolledAsync", () => {
  it("re-fetches on the interval until stopWhen is satisfied", async () => {
    const statuses = ["pending", "assigned", "done"];
    let call = 0;
    const fetcher = vi.fn().mockImplementation(async () => {
      const status = statuses[Math.min(call, statuses.length - 1)];
      call += 1;
      return { status };
    });

    const { result } = renderHook(() =>
      usePolledAsync(fetcher, {
        pollIntervalMs: 1,
        stopWhen: (data: { status: string }) => data.status === "done",
      }),
    );

    await waitFor(() => {
      expect(result.current).toEqual({ status: "success", data: { status: "done" } });
    });

    expect(fetcher).toHaveBeenCalledTimes(3);
  });

  it("stops polling and reports an error if the fetch rejects", async () => {
    const fetcher = vi.fn().mockRejectedValue(new Error("boom"));

    const { result } = renderHook(() =>
      usePolledAsync(fetcher, { pollIntervalMs: 1, stopWhen: () => false }),
    );

    await waitFor(() => {
      expect(result.current).toEqual({ status: "error", message: "boom" });
    });

    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
