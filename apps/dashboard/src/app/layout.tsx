import Link from "next/link";
import type { ReactNode } from "react";

export const metadata = { title: "Gauntlet dashboard" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui", margin: "2rem auto", maxWidth: 960, padding: "0 16px" }}>
        <nav style={{ marginBottom: "1.5rem", display: "flex", gap: 12, flexWrap: "wrap" }}>
          <Link href="/">Overview</Link>
          <Link href="/gate">Gate</Link>
          <Link href="/recall">Recall</Link>
          <Link href="/recall/review">Review queue</Link>
          <Link href="/sponsors">Sponsor proof</Link>
          <Link href="/onboarding">Onboarding</Link>
          <Link href="/login">Reviewer login</Link>
          <span style={{ color: "#999" }}>|</span>
          <Link href="/gate/offline">Offline gate (P0)</Link>
          <Link href="/fake-run">Fake run</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
