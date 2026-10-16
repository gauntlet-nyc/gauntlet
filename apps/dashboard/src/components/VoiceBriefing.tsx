"use client";

import { Square, Volume2 } from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";

// Resting bar heights (0..1); deterministic so server and client render the same.
const BARS = [0.4, 0.75, 1, 0.6, 0.85, 0.5, 0.9, 0.45, 0.7, 0.55, 0.95, 0.5];
const BAR_WIDTH = 2;
const BAR_GAP = 2;
const WAVE_HEIGHT = 16;

function Waveform() {
  const reduce = useReducedMotion();
  const width = BARS.length * (BAR_WIDTH + BAR_GAP) - BAR_GAP;
  return (
    <svg viewBox={`0 0 ${width} ${WAVE_HEIGHT}`} width={width} height={WAVE_HEIGHT} className="text-foreground" aria-hidden>
      {BARS.map((h, i) => {
        const rest = Math.max(2, h * WAVE_HEIGHT * 0.35);
        const peak = h * WAVE_HEIGHT;
        return (
          <motion.rect
            key={i}
            x={i * (BAR_WIDTH + BAR_GAP)}
            width={BAR_WIDTH}
            rx={1}
            fill="currentColor"
            initial={{ height: rest, y: (WAVE_HEIGHT - rest) / 2 }}
            animate={
              reduce
                ? { height: peak * 0.6, y: (WAVE_HEIGHT - peak * 0.6) / 2 }
                : { height: [rest, peak, rest], y: [(WAVE_HEIGHT - rest) / 2, (WAVE_HEIGHT - peak) / 2, (WAVE_HEIGHT - rest) / 2] }
            }
            transition={reduce ? { duration: 0 } : { duration: 0.9 + (i % 4) * 0.15, repeat: Infinity, ease: "easeInOut", delay: (i % 5) * 0.06 }}
          />
        );
      })}
    </svg>
  );
}

// Plays the templated briefing. With `audioUrl` the voice is ElevenLabs (synthesized by the API);
// otherwise it falls back to the browser's own speech engine and says so.
export function VoiceBriefingButton({
  text,
  providerLabel,
  audioUrl,
}: {
  text: string;
  providerLabel: string;
  audioUrl?: string;
}) {
  const [speaking, setSpeaking] = useState(false);
  const [loading, setLoading] = useState(false);
  const [supported, setSupported] = useState(true);
  const [useBrowser, setUseBrowser] = useState(!audioUrl);
  const audioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    const available = Boolean(audioUrl) || (typeof window !== "undefined" && "speechSynthesis" in window);
    setSupported(available);
    return () => {
      audioRef.current?.pause();
      if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
    };
  }, [audioUrl]);

  const speakWithBrowser = () => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };

  const toggle = () => {
    if (speaking) {
      audioRef.current?.pause();
      if (typeof window !== "undefined" && "speechSynthesis" in window) window.speechSynthesis.cancel();
      setSpeaking(false);
      return;
    }
    if (!audioUrl || useBrowser) {
      speakWithBrowser();
      return;
    }
    const audio = audioRef.current ?? new Audio(audioUrl);
    audioRef.current = audio;
    audio.onended = () => setSpeaking(false);
    audio.onerror = () => {
      // ElevenLabs unavailable: say it with the browser instead, and label it honestly.
      setLoading(false);
      setUseBrowser(true);
      speakWithBrowser();
    };
    audio.onplaying = () => {
      setLoading(false);
      setSpeaking(true);
    };
    setLoading(true);
    audio.currentTime = 0;
    void audio.play().catch(() => audio.onerror?.(new Event("error")));
  };

  const voiceLabel = audioUrl && !useBrowser ? "Voiced by ElevenLabs." : "Browser speech, not ElevenLabs.";

  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button type="button" variant="outline" size="sm" onClick={toggle} disabled={!supported || loading} className="h-7 gap-2 rounded-full px-3 text-xs">
          {speaking ? <Square className="size-3 fill-current" aria-hidden /> : <Volume2 className="size-3.5" aria-hidden />}
          {loading ? "Generating…" : speaking ? "Stop" : "Listen"}
          <AnimatePresence initial={false}>
            {speaking && (
              <motion.span initial={{ opacity: 0, width: 0 }} animate={{ opacity: 1, width: "auto" }} exit={{ opacity: 0, width: 0 }} className="overflow-hidden">
                <Waveform />
              </motion.span>
            )}
          </AnimatePresence>
        </Button>
      </TooltipTrigger>
      <TooltipContent side="bottom" align="end" className="max-w-xs text-xs leading-relaxed">
        <p>&ldquo;{text}&rdquo;</p>
        <p className="mt-1.5 opacity-70">
          {voiceLabel} {providerLabel}
        </p>
      </TooltipContent>
    </Tooltip>
  );
}
