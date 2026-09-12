"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

const workspaceLinks = [
  { href: "/", label: "Overview" },
  { href: "/catalogue", label: "Catalogue" },
  { href: "/requests", label: "Request console" },
  { href: "/quality", label: "Data quality" },
];

const manageLinks = [
  { href: "/benefits", label: "Benefit records" },
  { href: "/settings", label: "Settings" },
];

function Navigation({ links }: { links: typeof workspaceLinks }) {
  const pathname = usePathname();

  return (
    <nav>
      {links.map((link) => (
        <Link className={`nav-item ${pathname === link.href ? "active" : ""}`} href={link.href} key={link.href}>
          {link.label}
        </Link>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <main className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/"><span className="brand-mark">B</span><span>BondLayer</span></Link>
        <p className="nav-label">Workspace</p>
        <Navigation links={workspaceLinks} />
        <p className="nav-label">Manage</p>
        <Navigation links={manageLinks} />
      </aside>
      <section className="workspace">
        <header className="topbar">
          <label className="search"><span aria-hidden="true">⌕</span><input aria-label="Search" placeholder="Search requests or products" /></label>
          <div className="account"><span>12 Sep 2026</span><span className="avatar">HT</span><strong>Harbor Tech</strong></div>
        </header>
        {children}
      </section>
    </main>
  );
}
