"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { ArrowUp, Bell, ChevronDown, CircleHelp, ClipboardList, Gift, LayoutDashboard, Mic, Package, Settings, ShieldCheck } from "lucide-react";
import { Activity } from "lucide-react";

const workspaceLinks = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/catalogue", label: "Catalogue", icon: Package },
  { href: "/requests", label: "Request console", icon: ClipboardList },
  { href: "/analytics", label: "Analytics", icon: Activity },
  { href: "/quality", label: "Data quality", icon: ShieldCheck },
];

const manageLinks = [
  { href: "/benefits", label: "Benefit records", icon: Gift },
  { href: "/settings", label: "Settings", icon: Settings },
];

function Navigation({ links }: { links: Array<{ href: string; label: string; icon: LucideIcon }> }) {
  const pathname = usePathname();

  return (
    <nav>
      {links.map((link) => (
        <Link className={`nav-item ${pathname === link.href ? "active" : ""}`} href={link.href} key={link.href}>
          <link.icon size={16} strokeWidth={2} aria-hidden="true" /><span>{link.label}</span>
        </Link>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();

  if (pathname.startsWith("/onboarding")) {
    return <>{children}</>;
  }

  return (
    <main className="app-shell">
      <aside className="sidebar">
        <Link className="brand" href="/"><span className="brand-mark"><Image src="/console/bondlayer-logo.svg" alt="" width={246} height={237} priority /></span><span>BondLayer</span></Link>
        <p className="nav-label">Workspace</p>
        <Navigation links={workspaceLinks} />
        <p className="nav-label">Manage</p>
        <Navigation links={manageLinks} />
      </aside>
      <section className="workspace">
        <header className="topbar">
          <label className="search"><span aria-hidden="true">⌕</span><input aria-label="Search" placeholder="Search requests or products" /></label>
          <div className="topbar-tools"><button className="icon-button" type="button" aria-label="Help" title="Help"><CircleHelp size={17} strokeWidth={2} /></button><button className="icon-button notification-button" type="button" aria-label="Notifications" title="Notifications"><Bell size={17} strokeWidth={2} /></button><div className="account"><span className="avatar"><Image src="/console/bondlayer-logo.svg" alt="" width={34} height={34} sizes="34px" /></span><div className="account-copy"><strong>Merchant console</strong><span>Seeded demo merchants</span></div><ChevronDown size={15} strokeWidth={2} aria-hidden="true" /> </div></div>
        </header>
        <div className="page-transition" key={pathname}>{children}</div>
        <form className="prompt-bar" onSubmit={(event) => event.preventDefault()}>
          <span className="prompt-mark" aria-hidden="true">✦</span>
          <input aria-label="Ask BondLayer" placeholder="Ask BondLayer about your catalogue, agents or next fix..." />
          <button className="voice-button" type="button" aria-label="Use voice input" title="Use voice input"><Mic size={16} strokeWidth={2.2} /></button><button type="submit" aria-label="Send prompt" title="Send prompt"><ArrowUp size={16} strokeWidth={2.4} /></button>
        </form>
      </section>
    </main>
  );
}
