/**
 * Session helpers for the dashboard. The dashboard never verifies the
 * OIDC token itself — the Gateway does that and issues a signed session
 * cookie. This module only reads the current-user info the Gateway
 * exposes and redirects to /auth/login when unauthenticated.
 */

const GATEWAY_URL = process.env.NEXT_PUBLIC_GATEWAY_URL ?? "";

export interface CurrentUser {
  subject: string;
  tenantId: string;
  role: string;
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  const response = await fetch(`${GATEWAY_URL}/api/v1/me`, {
    credentials: "include",
  });

  if (response.status === 401) {
    return null;
  }

  if (!response.ok) {
    throw new Error(`Failed to resolve current user (${response.status})`);
  }

  return (await response.json()) as CurrentUser;
}

export function redirectToLogin(): void {
  window.location.href = `${GATEWAY_URL}/auth/login`;
}
