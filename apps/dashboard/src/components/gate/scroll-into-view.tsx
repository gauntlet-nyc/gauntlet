"use client";

import { useEffect } from "react";

/** After a server-action redirect (which drops URL fragments), bring the acted-on card into view. */
export function ScrollIntoView({ targetId }: { targetId: string }) {
  useEffect(() => {
    document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [targetId]);
  return null;
}
