"use client";

import {
  Activity,
  Brain,
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
    </Sidebar>
  );
}
