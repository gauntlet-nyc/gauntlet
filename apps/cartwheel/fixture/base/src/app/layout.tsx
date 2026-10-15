import type { ReactNode } from "react";

export const metadata = { title: "Cartwheel" };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body style={{ fontFamily: "system-ui", margin: 0 }}>
        <header style={{ padding: "12px 16px", borderBottom: "1px solid #ddd" }}>Cartwheel</header>
        {children}
      </body>
    </html>
  );
}
