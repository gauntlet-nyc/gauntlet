"use client";

import {
  Activity,
  BookOpenCheck,
  Brain,
  FlaskConical,
  History,
  LayoutDashboard,
  ListChecks,
  LogIn,
  Rocket,
  ShieldCheck,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

import { LogoMark } from "./logo";

type NavItem = { href: string; label: string; icon: LucideIcon };

const NAV: { label: string; items: NavItem[] }[] = [
  {
    label: "Product",
    items: [
      { href: "/", label: "Overview", icon: LayoutDashboard },
      { href: "/gate", label: "Gate", icon: ShieldCheck },
      { href: "/recall", label: "Recall", icon: History },
      { href: "/recall/review", label: "Review queue", icon: ListChecks },
      { href: "/memory", label: "Memory", icon: Brain },
    ],
  },
  {
    label: "Platform",
    items: [
      { href: "/sponsors", label: "Sponsor proof", icon: Activity },
      { href: "/onboarding", label: "Onboarding", icon: Rocket },
      { href: "/login", label: "Reviewer login", icon: LogIn },
    ],
  },
  {
    label: "Diagnostics",
    items: [
      { href: "/gate/offline", label: "Offline gate (P0)", icon: FlaskConical },
      { href: "/fake-run", label: "Fake run", icon: BookOpenCheck },
    ],
  },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  if (href === "/recall") return pathname === "/recall";
  if (href === "/gate") return pathname === "/gate" || pathname.startsWith("/gate/runs");
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function AppSidebar() {
  const pathname = usePathname();
  return (
    <Sidebar collapsible="icon" variant="sidebar">
      <SidebarHeader className="px-3 pt-4 pb-2">
        <Link href="/" className="flex items-center gap-2.5 rounded-md px-1 py-1 outline-none">
          <LogoMark className="shrink-0" />
          <div className="flex min-w-0 flex-col leading-tight group-data-[collapsible=icon]:hidden">
            <span className="text-[15px] font-semibold tracking-tight">Gauntlet</span>
            <span className="text-muted-foreground text-[11px]">Adversarial release testing</span>
          </div>
        </Link>
      </SidebarHeader>
      <SidebarContent>
        {NAV.map((group) => (
          <SidebarGroup key={group.label}>
            <SidebarGroupLabel className="text-[11px] tracking-wide uppercase">{group.label}</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton asChild isActive={isActive(pathname, item.href)} tooltip={item.label}>
                      <Link href={item.href}>
                        <item.icon />
                        <span>{item.label}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter className="px-3 pb-4 group-data-[collapsible=icon]:hidden">
        <div className="border-sidebar-border rounded-lg border p-3 text-xs">
          <div className="text-foreground flex items-center gap-2 font-medium">
            <span className="bg-inconclusive size-1.5 rounded-full" />
            Synthetic target
          </div>
          <p className="text-muted-foreground mt-1 leading-relaxed">
            Cartwheel fixture. The model proposes; oracles and humans decide.
          </p>
        </div>
      </SidebarFooter>
    </Sidebar>
  );
}
