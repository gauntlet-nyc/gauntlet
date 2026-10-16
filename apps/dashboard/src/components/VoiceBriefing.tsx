"use client";

import { useState } from "react";

// Reads the templated briefing aloud with the browser's own speech engine. This is NOT
// ElevenLabs; the ElevenLabs voice is offline-tested only until its key is set and run live.
export function VoiceBriefingButton({ text, providerLabel }: { text: string; providerLabel: string }) {
  const [speaking, setSpeaking] = useState(false);
  const speak = () => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.onend = () => setSpeaking(false);
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  };
  return (
    <div>
      <button type="button" onClick={speak} disabled={speaking}>
        {speaking ? "Speaking…" : "▶ Play voice briefing"}
      </button>
      <p style={{ fontSize: 13 }}>&ldquo;{text}&rdquo;</p>
      <small style={{ color: "#555" }}>Voice: browser speech (not ElevenLabs). {providerLabel}</small>
    </div>
  );
}
