# Plan: Preserve native shell startup behavior

## Goal
Make SILC launch shells with their normal profile/init behavior intact, while still injecting SILC helpers afterward.

## Steps
1. Remove explicit profile suppression from shell launch specs.
2. Update bootstrap scripts so they layer SILC hooks on top of the user's native shell startup files.
3. Adjust tests to assert profile-preserving launch behavior.
4. Run targeted Python tests and fix any regressions.

## Notes
- PowerShell should stop using `-NoProfile`.
- Bash/Zsh should preserve user rc/profile behavior instead of bypassing it.
- Keep the session helper injection intact so `run`, cwd tracking, and prompt hooks still work.
