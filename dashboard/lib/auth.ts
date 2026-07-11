/**
 * Session helpers for the dashboard. The dashboard never verifies the
 * OIDC token itself — the Gateway does that and issues a signed session
 * cookie. This module only reads the current-user info the Gateway
 * exposes and redirects to /auth/login when unauthenticated.
 */

export interface CurrentUser {
  subject: string;
  tenantId: string;
  role: string;
}

export async function getCurrentUser(): Promise<CurrentUser | null> {
  throw new Error("not implemented");
}

export function redirectToLogin(): void {
  throw new Error("not implemented");
}
