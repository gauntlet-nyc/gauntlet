"use client";

import { useState } from "react";

import styles from "./FloatingHelp.module.css";

export function FloatingHelp() {
  const [open, setOpen] = useState(false);
  return (
    <div className={styles.floatingHelp}>
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
