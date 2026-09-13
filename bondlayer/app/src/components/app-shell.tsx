"use client";

import Link from "next/link";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { CircleHelp, ClipboardList, Gift, LayoutDashboard, Package, Settings, ShieldCheck } from "lucide-react";
import { AskBar } from "./ask-bar";
import { hasSeenTour, Walkthrough } from "@/components/walkthrough";
import { MerchantSwitcher } from "./merchant-switcher";
import { Failed, Loading } from "./states";
import { useMerchants } from "@/lib/api";

const workspaceLinks = [
  { href: "/", label: "Overview", icon: LayoutDashboard, tour: "nav-overview" },
  { href: "/catalogue", label: "Catalogue", icon: Package, tour: "nav-catalogue" },
  { href: "/requests", label: "Shopping insights", icon: ClipboardList, tour: "nav-requests" },
  { href: "/quality", label: "Data quality", icon: ShieldCheck, tour: "nav-quality" },
];

const manageLinks = [
  { href: "/benefits", label: "Benefit records", icon: Gift, tour: "nav-benefits" },
  { href: "/settings", label: "Settings", icon: Settings, tour: "nav-settings" },
];

function Navigation({ links }: { links: Array<{ href: string; label: string; icon: LucideIcon; tour: string }> }) {
  const pathname = usePathname();

  return (
    <nav>
      {links.map((link) => (
        <Link className={`nav-item ${pathname === link.href ? "active" : ""}`} href={link.href} key={link.href} data-tour={link.tour}>
          <link.icon size={16} strokeWidth={2} aria-hidden="true" /><span>{link.label}</span>
        </Link>
      ))}
    </nav>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [touring, setTouring] = useState(false);
  const merchants = useMerchants();
  const empty = !merchants.loading && merchants.data?.length === 0;
  useEffect(() => {
    if (empty && !pathname.startsWith("/onboarding")) router.replace("/onboarding/");
  }, [empty, pathname, router]);

  // First visit to the overview starts the tour once; the help button replays it.
  useEffect(() => {
    if (pathname !== "/" || !merchants.data?.length || hasSeenTour()) return;
    const timer = window.setTimeout(() => setTouring(true), 600);
    return () => window.clearTimeout(timer);
  }, [pathname, merchants.data]);

  const startTour = () => {
    if (pathname !== "/") router.push("/");
    setTouring(true);
  };

  if (pathname.startsWith("/onboarding")) {
    return <>{children}</>;
  }

  if (merchants.error) return <Failed what="your merchants" error={merchants.error} />;
  if (merchants.loading && !merchants.data) return <Loading what="your merchants" />;
  if (empty) return <p className="state-note">No merchants yet. <Link href="/onboarding/">Start onboarding →</Link></p>;

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
          <MerchantSwitcher />
          <div className="topbar-tools"><Link className="upload-button" href="/onboarding/">Add merchant</Link><button className="icon-button" type="button" aria-label="Replay the console tour" title="Replay the console tour" data-tour="help" onClick={startTour}><CircleHelp size={17} strokeWidth={2} /></button><div className="account"><span className="avatar"><Image src="/console/bondlayer-logo.svg" alt="" width={34} height={34} sizes="34px" /></span><div className="account-copy"><strong>Merchant console</strong><span>Your uploaded catalogues</span></div></div></div>
        </header>
        <div className="page-transition" key={pathname}>{children}</div>
        <AskBar />
      </section>
      <Walkthrough open={touring} onClose={() => setTouring(false)} />
    </main>
  );
}
