# Daytona environment adapter (owner B)

Phase 0: verify `daytona` Python SDK and environment access. Phase 1: create equivalent base/head test sandboxes, expose allowed target preview to Anchor, verify startup and fixture checksum, clean up. Use eligible VM for `sandbox.fork`; container sandbox has cold snapshot/recreate fallback. Never inject provider keys or benchmark truth into the target VM.
