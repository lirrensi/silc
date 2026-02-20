---
name: shared-shell-usage
description: Guide an agent to install SILC, create SharedShell sessions, run commands, and keep a human collaborator informed while working in parallel.
---

# Confirm SILC is installed before touching shells
1. Run `silc --help` to check whether the CLI is on PATH and the 'start' command is available.
2. If `silc` is missing, install from the repo root with `pip install -e .` or, when possible, `pipx install git+https://github.com/lirrensi/silc.git` (also `uv tool install git+https://github.com/lirrensi/silc.git`); if pip cannot reach the network, run `install.bat` on Windows or `install.sh` on Unix.
3. After installation, re-run `silc --help` and then `silc start` to be sure commands resolve quickly before proceeding.

# Start the daemon and create the first session
1. Run `silc start` (optionally `silc start --port 8000`) so the daemon listens for shell sessions.
2. Execute `silc create` to get your first session; note the port that is printed and feed it to later commands.
3. Use `silc <port> status` and `silc <port> out` to verify the session is alive and seeing a shell prompt before running work.

# Spawn additional shells for parallel work
1. When you need parallel threads, run `silc create --port <port>` for each new shell so you can isolate tasks; the daemon accepts ports in the configured range (default 20000-21000).
2. Keep track of every session via `silc list`, include the port in reports to the human, and mention which port handles which task.
3. Use `silc <port> status`, `silc <port> logs`, or `silc <port> out 50` to confirm each shell remains responsive, and retire sessions with `silc <port> close` or `silc <port> kill` when done.

# Keep the human collaborator informed
1. After creating or selecting a session, send the human the port number and mention which task the session is covering.
2. Encourage the human to inspect output with `silc <port> out`, open the web UI with `silc <port> web` or the TUI with `silc <port> tui`, or just run `silc list` to see live shell health.
3. Provide them summaries of key outputs, echo the commands that were run, and point them to `silc logs` if deeper diagnostics are needed.
4. Mention in your status updates when you are waiting on them so they know to look inside the correct session instead of creating a new one.

# Choose the right command channel and read output
1. Use `silc <port> run "<command>"` to execute discrete commands; SILC manages the sentinel, returns the command output, and clears the prompt so you can read results with `silc <port> out`.
2. Use `silc <port> in "<text>"` when the running shell already expects input (for example, responding to a prompt or typing keystrokes in an interactive editor); `in` simply writes bytes to STDIN and does not wrap them in a new command, so include newline characters yourself when needed.
3. Always follow `run` or `in` with `silc <port> out` to grab the latest output, and check `silc <port> status` to know whether the shell is waiting for more input before sending another `in`.
4. Prefer `run` for idempotent commands and `in` for continuing an interactive session; mixing them without observing `out` can desynchronize your view of the shell.
