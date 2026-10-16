import { AlertTriangle, CheckCircle2, Info, LogOut, ShieldCheck, type LucideIcon } from "lucide-react";
import { cookies } from "next/headers";
import type { ReactNode } from "react";

import { login, logout } from "@/app/actions";
import { Reveal } from "@/components/motion/reveal";
import { LogoMark } from "@/components/shell/logo";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

export const dynamic = "force-dynamic";

type NoticeTone = "bad" | "good" | "info";

const NOTICE_STYLES: Record<NoticeTone, { className: string; icon: LucideIcon }> = {
  bad: { className: "border-regression/30 bg-regression/[0.07] text-regression", icon: AlertTriangle },
  good: { className: "border-passed/30 bg-passed/[0.07] text-passed", icon: CheckCircle2 },
  info: { className: "border-info/30 bg-info/[0.07] text-info", icon: Info },
};

function Notice({ tone, role, children }: { tone: NoticeTone; role: "alert" | "status"; children: ReactNode }) {
  const { className, icon: Icon } = NOTICE_STYLES[tone];
  return (
    <p role={role} className={cn("flex items-start gap-2.5 rounded-lg border px-3 py-2.5 text-[13px]", className)}>
      <Icon className="mt-0.5 size-3.5 shrink-0" aria-hidden />
      <span>{children}</span>
    </p>
  );
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const query = await searchParams;
  const signedIn = Boolean((await cookies()).get("gauntlet_reviewer_token"));
  return (
    <main className="flex justify-center pt-6 md:pt-16">
      <Reveal className="w-full max-w-[400px]">
        <div className="bg-card rounded-xl border shadow-[0_1px_0_0_oklch(1_0_0/4%)_inset,0_24px_48px_-24px_oklch(0_0_0/60%)]">
          <div className="px-6 pt-7 pb-6 sm:px-8">
            <LogoMark className="size-9" />
            <div className="mt-5 flex items-center gap-2">
              <h1 className="text-xl font-semibold tracking-tight">Reviewer login</h1>
              <span className="text-muted-foreground rounded-full border px-2 py-px text-[10.5px] font-medium tracking-wide uppercase">
                Dev-grade
              </span>
            </div>
            <p className="text-muted-foreground mt-2 text-sm leading-relaxed">
              Paste a reviewer token configured on the API. It is kept in an httpOnly cookie on this dashboard server and
              is never shown again. Demo use only.
            </p>

            {(query.error === "short" || query.ok || query.next) && (
              <div className="mt-5 space-y-2">
                {query.error === "short" && (
                  <Notice tone="bad" role="alert">
                    Token must be at least 16 characters.
                  </Notice>
                )}
                {query.ok && (
                  <Notice tone="good" role="status">
                    Token stored. The API checks it on every approval.
                  </Notice>
                )}
                {query.next && (
                  <Notice tone="info" role="status">
                    Log in to record that decision, then go back.
                  </Notice>
                )}
              </div>
            )}

            <form action={login} className="mt-6 space-y-3">
              <div className="space-y-2">
                <Label htmlFor="token">Reviewer token</Label>
                <Input
                  id="token"
                  name="token"
                  type="password"
                  autoComplete="off"
                  placeholder="reviewer token"
                  className="font-mono placeholder:font-sans"
                  aria-invalid={query.error === "short" || undefined}
                />
              </div>
              <Button type="submit" className="w-full">
                Store token
              </Button>
            </form>
          </div>

          <div className="bg-muted/30 flex items-center justify-between gap-3 rounded-b-xl border-t px-6 py-3 sm:px-8">
            {signedIn ? (
              <>
                <span className="text-foreground inline-flex items-center gap-2 text-[13px]">
                  <ShieldCheck className="text-passed size-4" aria-hidden />
                  Signed in as a reviewer
                </span>
                <form action={logout}>
                  <Button type="submit" variant="ghost" size="sm" className="text-muted-foreground -mr-2">
                    <LogOut aria-hidden />
                    Log out
                  </Button>
                </form>
              </>
            ) : (
              <span className="text-muted-foreground text-xs leading-relaxed">
                Tokens come from <code className="text-foreground/80 font-mono">GAUNTLET_REVIEWER_TOKENS</code> on the API.
              </span>
            )}
          </div>
        </div>
      </Reveal>
    </main>
  );
}
