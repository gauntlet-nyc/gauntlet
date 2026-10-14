import Link from "next/link";
import type { ReactNode } from "react";

export const metadata = { title: "Gauntlet dashboard" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui", margin: "2rem auto", maxWidth: 760 }}>
        <nav style={{ marginBottom: "1.5rem" }}>
          <Link href="/">Overview</Link> · <Link href="/fake-run">Fake run</Link>
        </nav>
        {children}
      </body>
    </html>
  );
}
