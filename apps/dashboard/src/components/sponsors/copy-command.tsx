"use client";

import { Check, Copy } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

const RESET_MS = 1600;

/** A shell command in a code block with a copy button. */
export function CopyCommand({ command, className }: { command: string; className?: string }) {
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  const reduce = useReducedMotion();

  useEffect(() => {
    if (!copied && !failed) return;
    const t = window.setTimeout(() => {
      setCopied(false);
      setFailed(false);
    }, RESET_MS);
    return () => window.clearTimeout(t);
  }, [copied, failed]);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard.writeText(command);
      setCopied(true);
    } catch {
      // Clipboard can be blocked (insecure context, permissions); say so instead of pretending.
      setFailed(true);
    }
  }

  const label = copied ? "Copied" : failed ? "Copy blocked by the browser" : "Copy command";
  const swap = reduce ? {} : { initial: { scale: 0.6, opacity: 0 }, animate: { scale: 1, opacity: 1 }, exit: { scale: 0.6, opacity: 0 } };

  return (
    <div className={cn("bg-background/60 group/cmd relative rounded-lg border", className)}>
      <pre className="py-2.5 pr-11 pl-3 font-mono text-[11.5px] leading-5 whitespace-pre-wrap [overflow-wrap:anywhere]">
        <span className="text-muted-foreground/60 select-none">$ </span>
        <span className="text-foreground/90">{command}</span>
      </pre>
      <button
        type="button"
        onClick={copy}
        aria-label={label}
        title={label}
        className="text-muted-foreground hover:text-foreground hover:bg-accent focus-visible:ring-ring/50 absolute top-1.5 right-1.5 flex size-7 items-center justify-center rounded-md transition-colors outline-none focus-visible:ring-[3px]"
      >
        <AnimatePresence mode="wait" initial={false}>
          {copied ? (
            <motion.span key="check" {...swap} transition={{ duration: 0.15 }} className="text-passed">
              <Check className="size-3.5" aria-hidden />
            </motion.span>
          ) : (
            <motion.span key="copy" {...swap} transition={{ duration: 0.15 }}>
              <Copy className="size-3.5" aria-hidden />
            </motion.span>
          )}
        </AnimatePresence>
      </button>
      <span className="sr-only" role="status" aria-live="polite">
        {copied ? "Command copied" : failed ? "Copy blocked by the browser" : ""}
      </span>
    </div>
  );
}
