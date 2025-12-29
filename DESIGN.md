silc (Shared Interactive Linked CMD) - give your agent a terminal to work with!

Problem: coding agents cant attach to any existing shell, only open new and even that is in the background.
Also cant just do stuff in current shell - simple continuous task required waiting for results, they are essentially sync.
Problem having a stable shell that it can keep and check outputs from time to time - important for long running tasks!
Even if they could - they usually do p.open and own the process! If it crashes - fail, and also you cant look inside!

You cant just: "here is terminal X go check inside and tell me whats wrong" or "open ssh on there and config me serv" (while running agent from local machine, not in there)

Solution: wrap a shell with simple rest api.
1. You open simple pyz app instead of regular cmd
2. It creates a GUI for shell like + exposes rest server to read/write.
3. You can still see and type. Any app can see and type in.

Why not pipes/handles tty?
Initial idea was to expose terminal as file - so one can `cat` or `echo` in. Just point agent to file.
But problem: GUI sync, else one cant look inside.
TTY: works fine on unix, impossible on win.
To do both read and write at same time - would require 2 files - one for read and write, also locks and potential async hell.

Rest server makes it easier and more accessible.

How it works:
1. start: silc start => spawns a server at port (any in 20000+ range until finds ok)
    => inherits current shell, like in win - cmd/pwsh would open same! (also even current dir|os.environ for max easy!)
    => not really inherits as is but just env/path/all conditions
    => creates PTY/ConPTY
=> terminal opened at 21000 => also auto opens TUI!
2. silc 21000 open => activates TUI in current window (can open even 2 at same time! its just a UI!)
3. now its accessible from both api and in tui - can close and reopen later!
(gui is coming later if anyone wants)
4. all sessions saved in 
5. all lives in ./silc => ~/.silc/ (or %APPDATA%/silc on Windows) 

> exposes a list of commands:
silc 21000 out => returns last 100 lines (equiv of `cat`)
silc 21000 out 1000 => but 1k lines!
silc 21000 read (same)

silc 21000
silc 21000 stream
=> same but like tail -f | in rest does sse

silc 21000 in <text> => sends input into tty
silc 21000 write <text> (same)

silc 21000 run <text>
=> is a sync wrapper for case: send text, wait to completion and return result.
As still agent calling a tool expects a response, and doing in then immediately out may not be timed well!
`run`: send command - waits till it completes, then returns results out/err
Agent can possibly shoot itself in the foot by running it over long task but that smarts issue;

silc 21000 status => what running inside, down to what app is (or not)
silc 21000 clean => cleans buffer (raw), as is. if anything running, no matter;
silc 21000 interrupt => sends in ctrl C
silc 21000 close => sends gentle sigint, waits and  closes
silc 21000 kill => os level murder

> helper commands
silc list
silc killall

> Entire thing exists as rest api also!

curl GET localhost:21000/status
curl GET localhost:21000/out
curl GET localhost:21000/out?lines=1000

curl POST localhost:21000/in "text"
curl POST localhost:21000/clean/interrupt/close/kill



=====================================
stack: py fastapi, Textual, pyinstaller, all async first;

Gotchas:
- idle terminals garbage collected if not anything runs/checks them in last hr - but if any app runs - then ok
=> detect if: no child process is running + not accessed by anything last hr
- should be able to bridge networks, win<=>wsl + local, run as 0.0.0.0?
    => silc start -global => runs on whole network
    (later implement auth! or enjoy a literal rce hehe)
    also -port for make specific!
- win first! most used and wsl issues

- line buffered => using PTY wrapper instead, so we can read anytime!
BUT writes are may error if process running and not ready to accept? like input()?!

-  Windows sends \r\n. Linux sends \n. Your API should normalize \r\n to \n for output, but handle \r correctly for overwriting progress bars (like pip progress).


==========
brainstorm log:


The Issue: On Windows, you can't just pipe stdin/stdout and expect interactive apps (like vim, htop, or even python REPL) to work. They require a PTY.
The Fix: You need to use pywintrace or pyuv to wrap ConPTY. If you don't use ConPTY, your agent won't be able to handle anything that uses "colored text" or "interactive prompts" correctly—it will just see a mess of ANSI escape codes or nothing at all.
Library Suggestion: Use pyte (an in-memory terminal emulator). It maintains the "state" of the screen so your API can return exactly what the user sees, rather than a raw byte stream.

Your run command (Wait for completion) is the hardest part of the logic.
The Issue: In a TTY/Shell, there is no "finished" event unless the process exits. If an agent runs ls, the shell stays open. How does SILC know the command is done and it's time to return the output to the agent?
Potential Solution: You’ll need to look for the Shell Prompt (e.g., user@machine:~$).
Better Solution: When using run, SILC could inject a unique marker into the stream (e.g., echo [SILC-FINISHED-XYZ]) and wait for that string to appear in the output.


Agents (LLMs) are terrible at reading raw ANSI escape codes (the stuff that makes text bold or moves the cursor).
The Issue: If the agent runs pip install, it gets flooded with \r and progress bar frames.
The Fix: Your API (/out) should probably have a ?strip_ansi=true flag. Send the agent cleaned, plain text. Keep the raw stuff for your TUI.
=> JUST ALWWAYS STRIP empty


7. Feedback Loop (The "Type-ahead" bug)
If a user is typing in the TUI while the Agent is sending a command via the API:
The Issue: Characters will interleave. g-i-t-S-I-L-C-s-t-a-t-u-s.
The Fix: Implement a "Lock" mechanism. If the API is "Running," the TUI input should be temporarily disabled (or warned) to avoid corrupting the command.
Add a session “input mutex” with clear ownership:
/lock returns token; /in can optionally require token; TUI respects lock too.
Or implement atomic “send line” semantics (queue by line, not by keystroke), though that breaks full-screen apps. (better)

Environment Sync: When silc start is called, it must capture the current shells PATH. If I'm in a Conda env, silc needs to inherit that or the agent will have the wrong Python.
=> !important! should inherit venv literally endless fucking problem

Zombie Processes: If silc crashes, ensure it kills the child shell (use atexit and sub-process groups).


6) Buffering and memory: logs can explode
Long-running commands (pip install, builds) can generate huge output.
If you store everything in memory, it’ll balloon; if you store on disk, you need rotation and indexing.
Recommendation:
Use a ring buffer (size in bytes + time window).
Persist to disk with rotation if you want “reopen later”.
/out?since=<cursor> style APIs scale better than “give me last N lines”.
=> keep max 1k lines basically



PTY rendering hell:
- simple first approach:
    - get raw bytes + decode
    - Textual gets directly - renders itself;
    - most of commands would be simple `ls` echo and so on
    - read returns most rendered text
    also default we get 100 lines: if that is processing like - sees for that it is
    but if done - then will see final output!

    but also `run` issue: we want to run a command THEN wait and get ONLY the final out! 
    oh fuck that is an issue... maybe?
    Then add a cozy run endpoint:
    Send command + "\n"
    Snapshot buffer position
    Poll/read until output stops changing for ~2s (idle = done!)
    Return only the new delta text (final clean-ish output)

    Practical design:

    For run, do sentinel injection:
    Send: <command>; echo __SILC_DONE__<uuid>__:$LASTEXITCODE (pwsh differs) etc.
    Wait until sentinel appears in the output stream.
    But you must handle:
    Shell differences: bash vs zsh vs cmd.exe vs pwsh syntax for exit code and separators.
    Quoting: ensure <command> doesn’t break your wrapper.
    Binary output: sentinel might be delayed due to buffering if you’re not truly in a PTY.
    Timeouts: run must support timeout + cancel.
    Recommendation: run should be explicitly “best effort”, with:

    timeout, max_output_bytes, and on_timeout behavior (return partial + “still running”).
    A separate exec endpoint that runs a one-shot command not inside the interactive shell (clean semantics) for cases where interactive context is not needed.

    Treat the PTY stream as bytes; decode with UTF-8 with replacement (configurable).
    In “clean transcript” mode, interpret \r overwrites and backspaces (or rely on terminal emulator rendering).

    pty => is as is - all runs inside
    open tui => renders raw output + redirect input

    slic commands | api => get clean text + redirect input same way
┌─────────────────────────────────────┐
│         PTY (Raw Reality)           │
│  - ANSI codes, \r overwrites, etc   │
│  - Actual shell process lives here  │
│  - "Source of truth"                │
└──────────────┬──────────────────────┘
               │
       ┌───────┴────────┐
       │                │
       ▼                ▼
┌─────────────┐  ┌──────────────┐
│     TUI     │  │  API/Commands│
│             │  │              │
│ Gets: RAW   │  │ Gets: CLEAN  │
│ Shows: Raw  │  │ Returns:     │
│ ANSI colors │  │ - Stripped   │
│ + fancy UI  │  │ - Collapsed  │
│             │  │ - Agent-ready│
└─────────────┘  └──────────────┘
       │                │
       └────────┬───────┘
                ▼
         Same input path
         (both write to PTY)

Why This Is Perfect 💕
1. PTY = Single Source of Truth

One process, one shell session
No synchronization hell
TUI and API are just different "views" of the same thing

2. TUI Gets Raw = Good UX

Human sees pretty colors
Human sees progress bars animate
Human can use it normally
It's a "real" terminal experience

3. API Gets Clean = Good DX

Agent doesn't see \x1b[32m garbage
Agent sees final state of progress bars
Agent gets "text that makes sense"
Easy to parse, easy to understand

4. Input Path Is Same = No Conflicts

Whether typed in TUI or sent via API
All goes to same PTY
No weird race conditions
Simple mental model

Agents are terrible with escape codes. Make cleaned output the default:
GET /out          # stripped (agent-friendly)
GET /out?raw=true # raw ANSI (for TUI)

---

A) Resizing
Full-screen apps need correct terminal size. When TUI attaches/detaches:
If you don’t propagate window resize to PTY/ConPTY, output will wrap incorrectly or apps break.
=> should not be an issue as PTY is the main, TUI is a renderer over it! pty stays 'default'

C) “/clean” semantics
If you clean the buffer while a client is streaming, what happens? You want a stable cursor model.
=> just yolo it for now



====
# You MUST have this or agents will hang forever
silc 21000 run "sleep 3600" --timeout 30
```
Default timeout of like 30-60s, with clear error messages.


write in mutex = - Queue user input until unlocked
anyone writes: locks for 1 sec; => on enter;

### The "Multiple Clients" Race Condition
What if TWO agents try to use the same terminal?
```
Agent A: silc 21000 run "npm install"
Agent B: silc 21000 run "rm -rf /"  # 😱
You need either:

Per-client sessions (different ports)
Request queuing with client IDs
Exclusive lock mechanism => THIS - only one run command can exists inside!