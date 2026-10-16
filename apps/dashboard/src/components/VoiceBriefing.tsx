"use client";

import { AudioLines, Pause, Play } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

// Resting bar heights (0..1) for the waveform; deterministic so server and client render the same.
const BARS = [0.35, 0.6, 0.9, 0.5, 0.75, 1, 0.55, 0.8, 0.4, 0.7, 0.95, 0.45, 0.65, 0.85, 0.5, 0.3, 0.6, 0.8, 0.4, 0.55];
const BAR_WIDTH = 3;
const BAR_GAP = 3;
const WAVE_HEIGHT = 28;

function Waveform({ active }: { active: boolean }) {
  const reduce = useReducedMotion();
  const width = BARS.length * (BAR_WIDTH + BAR_GAP) - BAR_GAP;
  return (
    <svg viewBox={`0 0 ${width} ${WAVE_HEIGHT}`} width={width} height={WAVE_HEIGHT} className="text-foreground" aria-hidden>
      {BARS.map((h, i) => {
        const rest = Math.max(3, h * WAVE_HEIGHT * 0.35);
        const peak = h * WAVE_HEIGHT;
        const animate = active && !reduce;
        return (
          <motion.rect
            key={i}
            x={i * (BAR_WIDTH + BAR_GAP)}
            width={BAR_WIDTH}
            rx={1.5}
            fill="currentColor"
            initial={false}
            animate={
              animate
                ? { height: [rest, peak, rest * 1.4, peak * 0.7, rest], y: [(WAVE_HEIGHT - rest) / 2, (WAVE_HEIGHT - peak) / 2, (WAVE_HEIGHT - rest * 1.4) / 2, (WAVE_HEIGHT - peak * 0.7) / 2, (WAVE_HEIGHT - rest) / 2], opacity: 0.9 }
                : { height: rest, y: (WAVE_HEIGHT - rest) / 2, opacity: 0.35 }
            }
            transition={animate ? { duration: 1.1 + (i % 5) * 0.12, repeat: Infinity, ease: "easeInOut", delay: (i % 7) * 0.05 } : { duration: 0.3 }}
          />
        );
      })}
    </svg>
  );
}

// Reads the templated briefing aloud with the browser's own speech engine. This is NOT
// ElevenLabs; the ElevenLabs voice is offline-tested only until its key is set and run live.
export function VoiceBriefingButton({ text, providerLabel }: { text: string; providerLabel: string }) {
  const [speaking, setSpeaking] = useState(false);
  const [supported, setSupported] = useState(true);

  useEffect(() => {
    setSupported(typeof window !== "undefined" && "speechSynthesis" in window);
    return () => {
      if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    };
  }, []);

  const toggle = () => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    if (speaking) {
      setSpeaking(false);
      return;
    }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  return (
    <div className="bg-background/60 flex h-full flex-col rounded-lg border p-4">
      <div className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
        <AudioLines className="size-3.5" aria-hidden />
        Voice briefing
      </div>
      <div className="mt-3 flex items-center gap-3">
        <Button
          type="button"
          size="icon"
          onClick={toggle}
          disabled={!supported}
          aria-label={speaking ? "Stop voice briefing" : "Play voice briefing"}
          className="size-9 shrink-0 rounded-full"
        >
          {speaking ? <Pause aria-hidden /> : <Play className="translate-x-px" aria-hidden />}
        </Button>
        <div className="min-w-0 flex-1 overflow-hidden">
          <Waveform active={speaking} />
        </div>
      </div>
      <p className={cn("text-muted-foreground mt-3 line-clamp-4 text-[13px] leading-relaxed", speaking && "text-foreground/90")}>
        &ldquo;{text}&rdquo;
      </p>
      <p className="text-muted-foreground/70 mt-auto pt-3 text-[11px] leading-snug">
        Browser speech, not ElevenLabs. {providerLabel}
      </p>
    </div>
  );
}
