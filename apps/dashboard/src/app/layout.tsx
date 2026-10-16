import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { AppSidebar } from "@/components/shell/app-sidebar";
import { Topbar } from "@/components/shell/topbar";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Gauntlet", template: "%s · Gauntlet" },
  description: "Change-aware adversarial release testing, and an audit of what already shipped.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" className={`dark ${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="font-sans">
        <TooltipProvider delayDuration={200}>
          <SidebarProvider>
            <AppSidebar />
            <SidebarInset className="bg-background min-w-0">
              <Topbar />
              <div className="relative flex-1">
                <div className="bg-grid mask-fade-b pointer-events-none absolute inset-x-0 top-0 h-72" aria-hidden />
                <div className="relative mx-auto w-full max-w-6xl px-4 pt-8 pb-24 md:px-8">{children}</div>
              </div>
            </SidebarInset>
          </SidebarProvider>
        </TooltipProvider>
        <Toaster />
      </body>
    </html>
  );
}
