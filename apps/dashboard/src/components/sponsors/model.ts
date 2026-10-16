import type { SponsorStatus } from "@/lib/gauntlet";

/** The only status the API uses once a recorded live run exists. Keys alone never produce it. */
export const LIVE_STATUS = "live verified";

export function isLive(s: SponsorStatus): boolean {
  return s.status === LIVE_STATUS;
}

/** What each provider powers inside Gauntlet, in a few words. */
export const POWERS: Record<string, string> = {
  Daytona: "Sandboxes",
  Anchor: "Cloud browser",
  "Arize AX": "Tracing",
  "SurrealDB core": "Run store",
  "SurrealDB Agent Memory": "Agent memory",
  ElevenLabs: "Voice briefings",
  "Azure OpenAI (planner)": "Attack planner",
  "AWS Bedrock (planner, alternate)": "Alternate planner",
  "GitHub App (check runs)": "Check runs",
};

/** Some sponsors have a note instead of a runnable command; only real commands get a copy button. */
const SHELL_COMMAND = /^[A-Z][A-Z0-9_]*=[^\s;]+\s|^(uv|pnpm|python|\.venv)\b/;

export function isShellCommand(command: string): boolean {
  return SHELL_COMMAND.test(command);
}
