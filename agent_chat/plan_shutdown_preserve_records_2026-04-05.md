# Plan: Preserve session records across shutdown/restart

Done means `silc shutdown` stops the daemon and closes live shells, but leaves desired session records intact so a later `silc start` / `silc manager` resurrects them automatically. `silc killall` remains the only destructive full wipe.

## Steps
1. [x] Change daemon shutdown cleanup so it closes runtime resources without removing registry records or rewriting `sessions.json`.
2. [x] Keep `killall` and per-session `close`/`kill` destructive as-is.
3. [x] Update CLI status messages/help text so shutdown implies preservation, not deletion.
4. [x] Add regression tests proving shutdown preserves records and restart/start reloads them.
5. [x] Refresh the daemon/CLI docs to match the preserved-record shutdown model.

## Verification
- Run targeted pytest coverage for daemon lifecycle and resurrect/restart flows.
- Confirm `sessions.json` still contains records after shutdown.
