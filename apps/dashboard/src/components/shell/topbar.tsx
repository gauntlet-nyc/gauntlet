"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Separator } from "@/components/ui/separator";
import { SidebarTrigger } from "@/components/ui/sidebar";

const LABELS: Record<string, string> = {
  gate: "Gate",
  runs: "Runs",
  recall: "Recall",
  review: "Review queue",
  memory: "Memory",
  sponsors: "Sponsor proof",
  onboarding: "Onboarding",
  login: "Reviewer login",
  offline: "Offline gate",
  cartwheel: "Cartwheel",
  "fake-run": "Fake run",
};

export function Topbar() {
  const pathname = usePathname();
  const parts = pathname.split("/").filter(Boolean);
  const crumbs = parts.map((part, i) => ({
    href: `/${parts.slice(0, i + 1).join("/")}`,
    label: LABELS[part] ?? decodeURIComponent(part),
    last: i === parts.length - 1,
  }));
  return (
    <header className="bg-background/70 sticky top-0 z-20 flex h-14 shrink-0 items-center gap-3 border-b px-4 backdrop-blur-xl md:px-6">
      <SidebarTrigger className="text-muted-foreground -ml-1" />
      <Separator orientation="vertical" className="!h-4" />
      <nav aria-label="Breadcrumb" className="text-muted-foreground flex min-w-0 items-center gap-1.5 text-sm">
        <Link href="/" className="hover:text-foreground transition-colors">
          Gauntlet
        </Link>
        {crumbs.map((c) => (
          <span key={c.href} className="flex min-w-0 items-center gap-1.5">
            <ChevronRight className="size-3.5 shrink-0 opacity-50" />
            {c.last ? (
              <span className="text-foreground truncate font-medium">{c.label}</span>
            ) : (
              <Link href={c.href} className="hover:text-foreground truncate transition-colors">
                {c.label}
              </Link>
            )}
          </span>
        ))}
      </nav>
      <div className="ml-auto flex items-center gap-2">
        <span className="text-muted-foreground hidden items-center gap-2 rounded-full border px-2.5 py-1 text-xs sm:inline-flex">
          <span className="bg-inconclusive relative flex size-1.5">
            <span className="bg-inconclusive absolute inline-flex size-full animate-ping rounded-full opacity-60" />
          </span>
          cartwheel-fixture
        </span>
      </div>
    </header>
  );
}
