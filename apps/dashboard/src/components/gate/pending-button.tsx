"use client";

import { Loader2 } from "lucide-react";
import type { ReactNode } from "react";
import { useFormStatus } from "react-dom";

import { Button } from "@/components/ui/button";

/** Submit button that shows a spinner while its parent form's server action runs. */
export function PendingButton({
  children,
  pendingLabel,
  icon,
  variant = "default",
  className,
}: {
  children: ReactNode;
  pendingLabel: string;
  /** A rendered icon element (components cannot cross the server/client boundary). */
  icon?: ReactNode;
  variant?: "default" | "outline" | "secondary";
  className?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" variant={variant} disabled={pending} aria-busy={pending} className={className}>
      {pending ? <Loader2 className="animate-spin" aria-hidden /> : icon}
      {pending ? pendingLabel : children}
    </Button>
  );
}
