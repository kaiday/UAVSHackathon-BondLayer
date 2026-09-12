import type { Metadata } from "next";
import { Figtree, Space_Grotesk } from "next/font/google";
import { AppShell } from "@/components/app-shell";
import "./globals.css";

const figtree = Figtree({
  variable: "--font-body",
  subsets: ["latin"],
});

const spaceGrotesk = Space_Grotesk({
  variable: "--font-display",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "BondLayer Merchant Console",
  description: "Make merchant value legible to AI shopping agents.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className={`${figtree.variable} ${spaceGrotesk.variable}`}>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
