"use client";

/**
 * Guards a page behind a resolved session: shows a loading state while
 * resolving the current user, redirects to the Gateway's OIDC login when
 * unauthenticated, and renders `children(user)` once resolved. Each page
 * wraps itself independently rather than gating at the layout level, so
 * a failed session check never blocks the shared nav from rendering.
 */

import { useEffect, useState } from "react";

import { getCurrentUser, redirectToLogin, type CurrentUser } from "@/lib/auth";

interface AuthGuardProps {
  children: (user: CurrentUser) => React.ReactNode;
}

type GuardState =
  | { status: "loading" }
  | { status: "authenticated"; user: CurrentUser }
  | { status: "redirecting" }
  | { status: "error"; message: string };

export function AuthGuard({ children }: AuthGuardProps) {
  const [state, setState] = useState<GuardState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;

    getCurrentUser()
      .then((user) => {
        if (cancelled) return;
        if (user === null) {
          setState({ status: "redirecting" });
          redirectToLogin();
          return;
        }
        setState({ status: "authenticated", user });
      })
      .catch((error: unknown) => {
        if (cancelled) return;
        setState({
          status: "error",
          message: error instanceof Error ? error.message : "Failed to resolve session",
        });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  if (state.status === "loading" || state.status === "redirecting") {
    return <p className="muted">Loading session…</p>;
  }

  if (state.status === "error") {
    return <p className="error-text">Could not verify your session: {state.message}</p>;
  }

  return <>{children(state.user)}</>;
}
