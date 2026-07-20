/**
 * Renders a useAsync() state: loading, a real error, a deliberate 501
 * ("this endpoint has no backing RPC yet" — see gateway/app/routers/*.py)
 * rendered as an honest "not available yet" notice rather than a crash
 * or a silently-empty list, or the resolved data via `children`.
 */

import type { AsyncState } from "@/lib/useAsync";

interface AsyncSectionProps<T> {
  state: AsyncState<T>;
  children: (data: T) => React.ReactNode;
}

export function AsyncSection<T>({ state, children }: AsyncSectionProps<T>) {
  if (state.status === "loading") {
    return <p className="muted">Loading…</p>;
  }

  if (state.status === "not_available") {
    return (
      <div className="notice notice-info">
        <strong>Not available yet.</strong> {state.detail}
      </div>
    );
  }

  if (state.status === "error") {
    return <div className="notice notice-error">{state.message}</div>;
  }

  return <>{children(state.data)}</>;
}
