"use client";

import { useState } from "react";

export function FloatingHelp() {
  const [open, setOpen] = useState(false);
  return (
    <div style={{ position: "fixed", bottom: 16, right: 16, zIndex: 50 }}>
      {open && (
        <div role="dialog" aria-label="Help" style={{ background: "#fff", border: "1px solid #ccc", padding: 12, marginBottom: 8 }}>
          Questions? Email help@example.invalid
        </div>
      )}
      <button type="button" data-testid="help-button" onClick={() => setOpen((o) => !o)} style={{ padding: "12px 20px" }}>
        Help
      </button>
    </div>
  );
}
