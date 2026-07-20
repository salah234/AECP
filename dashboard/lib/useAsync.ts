"use client";

/**
 * Shared data-fetching hook for dashboard pages: tracks loading/error/data
 * state for a single async call, re-running when `deps` changes. Kept
 * deliberately minimal (no caching, no revalidation) — this dashboard has
 * no data-fetching library dependency, and doesn't need one yet.
 */

import { useEffect, useState } from "react";

import { ApiError } from "@/lib/api-client";

export type AsyncState<T> =
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "not_available"; detail: string }
  | { status: "error"; message: string };

export function useAsync<T>(fetcher: () => Promise<T>, deps: unknown[] = []): AsyncState<T> {
  const [state, setState] = useState<AsyncState<T>>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });

    fetcher()
      .then((data) => {
        if (!cancelled) setState({ status: "success", data });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        if (error instanceof ApiError && error.status === 501) {
          setState({ status: "not_available", detail: error.detail });
        } else {
          setState({
            status: "error",
            message: error instanceof Error ? error.message : "Request failed",
          });
        }
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return state;
}
