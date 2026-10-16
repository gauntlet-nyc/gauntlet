"use client";

import { motion } from "motion/react";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

export interface NavSection {
  id: string;
  label: string;
}

/** Sticky in-page navigation that tracks which section is in view. */
export function SectionNav({ sections }: { sections: NavSection[] }) {
  const [active, setActive] = useState(sections[0]?.id ?? "");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries.filter((e) => e.isIntersecting).sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) setActive(visible[0].target.id);
      },
      { rootMargin: "-120px 0px -60% 0px" },
    );
    for (const s of sections) {
      const el = document.getElementById(s.id);
      if (el) observer.observe(el);
    }
    return () => observer.disconnect();
  }, [sections]);

  return (
    <nav aria-label="On this page" className="bg-background/80 sticky top-14 z-10 -mx-4 mt-8 border-b px-4 backdrop-blur-xl md:-mx-8 md:px-8">
      <ul className="-mb-px flex gap-1 overflow-x-auto [scrollbar-width:none]">
        {sections.map((s) => (
          <li key={s.id} className="relative shrink-0">
            <a
              href={`#${s.id}`}
              onClick={() => setActive(s.id)}
              className={cn(
                "block px-2.5 py-3 text-[13px] transition-colors",
                active === s.id ? "text-foreground" : "text-muted-foreground hover:text-foreground",
              )}
            >
              {s.label}
            </a>
            {active === s.id && (
              <motion.span layoutId="section-nav-underline" className="bg-foreground absolute inset-x-2 bottom-0 h-px" transition={{ duration: 0.25, ease: "easeOut" }} />
            )}
          </li>
        ))}
      </ul>
    </nav>
  );
}
