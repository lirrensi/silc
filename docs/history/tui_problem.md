# TUI Problem

**Initial problem**
- After running `python main.py start` and then `python main.py open 20000`, the TUI shows a constant stream of raw bytes instead of waiting for user input.
- The input field cannot accept Enter key presses, making it impossible to send commands.

**Why it happens**
- The PTY is left in raw mode when the session is started. When the API `open` attaches later, the PTY is not reset to canonical (line‑buffered) mode, so every byte the child process writes is echoed directly to the TUI.
- The design keeps the PTY state unchanged to allow other clients to attach to a live process, but this leaves the TUI in an unusable state.

**Possible solution**
- Provide a way to reset the PTY to canonical mode (or re‑initialize it) before the TUI connects.
- Expose an API endpoint (e.g. `/reset`) that calls `termios.tcsetattr`/`tty.setcbreak` on the PTY’s master file descriptor, or simply clears the buffer and sends a carriage‑return.
- The TUI client should invoke this reset (or `clear_buffer`) right after `open` so the stream stops and normal line‑buffered input resumes.

Implementing this reset will stop the constant byte stream and allow the user to press **Enter** to send commands again.

[considered done]