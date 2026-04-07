# Plan: Session wipe + full reset

_Fix `silc list` formatting, make `killall` clear session artifacts while keeping the daemon alive, and add a CLI-only `full-reset` for factory reset._

---

# Checklist
- [x] Step 1: Fix `silc list` idle-time formatting for missing values
- [x] Step 2: Change daemon/CLI `killall` to clear session records + artifacts, but keep daemon running
- [x] Step 3: Add CLI-only `full-reset` with confirmation and no API exposure
- [x] Step 4: Update docs/spec to reflect the new command split
- [x] Step 5: Run targeted validation

---

## Target behavior

- `shutdown` = graceful daemon stop, preserves session state
- `killall` = remove all current sessions and session artifacts, daemon keeps running
- `full-reset` = wipe SILC data back to a clean slate, stop daemon, remove pid/lock/artifacts, keep installed binaries
