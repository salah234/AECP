"use client";

/**
 * Shared top navigation, rendered once from the root layout. Fetches the
 * current user independently of any page-level AuthGuard purely for
 * display (who's logged in, which tenant) — it never redirects itself,
 * so a slow/failed session check here never blocks page content that
 * has its own AuthGuard.
 */

import Link from "next/link";
import { useEffect, useState } from "react";

import { getCurrentUser, type CurrentUser } from "@/lib/auth";

const LINKS = [
  { href: "/", label: "Overview" },
  { href: "/tasks", label: "Tasks" },
  { href: "/agents", label: "Agents" },
  { href: "/decisions", label: "Decisions" },
  { href: "/escalations", label: "Escalations" },
];

export function Nav() {
  const [user, setUser] = useState<CurrentUser | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCurrentUser()
      .then((resolved) => {
        if (!cancelled) setUser(resolved);
      })
      .catch(() => {
        // Nav display is best-effort; AuthGuard on the page itself is
        // the real enforcement point.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <header className="nav">
      <div className="nav-brand">AECP</div>
      <nav className="nav-links">
        {LINKS.map((link) => (
          <Link key={link.href} href={link.href}>
            {link.label}
          </Link>
        ))}
      </nav>
      <div className="nav-user">
        {user ? (
          <span title={`tenant ${user.tenantId}`}>
            {user.subject} · {user.role}
          </span>
        ) : (
          <span className="muted">not signed in</span>
        )}
      </div>
    </header>
  );
}
