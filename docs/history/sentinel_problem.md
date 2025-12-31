What you’re seeing is a logic bug in the “wait for sentinel” loop, not PowerShell randomly “breaking quotes”.

## What’s happening

### 1) You detect the sentinel in the *echoed input line* (too early)
Interactive shells echo back what you typed. Your `run` path appends the sentinel **to the command line** (via [`ShellInfo.get_sentinel_command()`](silc/utils/shell_detect.py:18)), so the echoed command line contains `__SILC_DONE_<id>__` *before the command has finished*.

In [`SilcSession.run_command()`](silc/core/session.py:114) you currently do:

- scan each buffered “line”
- `if sentinel in line:` treat that as completion

But the **first** line that often contains the sentinel is the echoed prompt line, e.g.:

`PS ...> whoami; echo "__SILC_DONE_xxxx__:$LASTEXITCODE"`

So your code hits the sentinel *inside that echoed command*, splits the line at the sentinel, and returns early with only the prefix:

`... whoami; echo "`  ← exactly the “always breaks apart” symptom

This comes straight from the split/overwrite logic in [`SilcSession.run_command()`](silc/core/session.py:138).

That also explains why `python main.py out ...` later shows the real output: the command actually ran; your `run` endpoint just declared “done” prematurely.

### 2) Your line buffering can split markers across reads (secondary issue)
Your PTY read loop appends arbitrary chunks, and [`RingBuffer.append()`](silc/core/buffer.py:18) does `splitlines()` on *each chunk independently*. If a marker or line is split across two reads, you can end up with fragments in separate “lines”, making matching unreliable in general.

This is a classic “treating a byte stream like message-framed lines” bug.

## How to solve it (robust approach)

### A) Only treat the sentinel as “done” when it looks like the sentinel *output line*
Make the completion condition stricter in [`SilcSession.run_command()`](silc/core/session.py:114):

- Ignore sentinel occurrences that are embedded inside the prompt/echo line.
- Only accept completion when the line (after minimal normalization) **starts with** the sentinel marker and includes an exit code.

Practical rule:
- accept only if `line.lstrip().startswith(sentinel)` (or a regex anchored at start like `^__SILC_DONE_<id>__:(-?\d+)`)

That single change prevents premature completion on:
- `PS ...> <cmd> ... "__SILC_DONE..."` (echoed input)

and waits for:
- `__SILC_DONE_xxxx__:0` (the `echo` output line)

You already have a prompt detector available as [`ShellInfo.prompt_pattern`](silc/utils/shell_detect.py:12); another valid strategy is “ignore lines matching the prompt pattern when searching for completion”, but anchoring on `startswith(sentinel)` is usually enough and simpler.

### B) Make sentinel parsing delimiter-based (so prompts can’t contaminate it)
Right now exit parsing is “scan tokens after sentinel for something digit-like” in [`SilcSession.run_command()`](silc/core/session.py:145). That breaks if prompt text ends up on the same line.

Better format (conceptually):
- print a line like: `__SILC_DONE_<id>__:0__END__`
- parse with a single anchored regex

This way you don’t care if extra junk appears after; you still reliably capture the exit code.

### C) Fix the buffer to be stream-correct (prevents “marker split across reads”)
Update buffering so it carries an incomplete trailing line between calls to [`RingBuffer.append()`](silc/core/buffer.py:18), rather than calling `splitlines()` on each chunk independently.

Conceptually:

- keep `self._partial` (text or bytes)
- append new chunk
- split on `\n` boundaries
- store the final unterminated fragment back into `self._partial`
- only commit complete lines to `self.lines`

This eliminates “random splits” of both:
- echoed command lines
- sentinel output lines

### D) (Optional) Search for sentinel in the raw stream, not “lines”
The most robust design is: treat PTY output as a byte stream and scan for `b"__SILC_DONE_<id>__:"` across chunk boundaries (a streaming substring search), then parse until newline. That completely sidesteps line-framing issues from [`RingBuffer.append()`](silc/core/buffer.py:18).

## Why this matches your transcript
Your “broken” line:

`> whoami; echo "`

is exactly what you get when the echoed command line is split at the sentinel and you return the prefix (`before`) per [`SilcSession.run_command()`](silc/core/session.py:139).

The later `out` shows the full, correct execution because the session kept running; the “done detector” just fired on the wrong occurrence.

## Dataflow (current vs fixed)

```mermaid
flowchart TD
  A[Client: POST /run] --> B[Session writes: cmd + sentinel echo]
  B --> C[Shell echoes input line (contains sentinel)]
  C --> D{Current: sentinel in line?}
  D -->|YES (too early)| E[Return truncated echoed line]
  B --> F[Shell runs cmd, prints real output + sentinel line]
  F --> G[User later calls /out and sees it]

  C --> H{Fixed: line starts with sentinel?}
  H -->|NO| I[Keep waiting]
  F --> J{Fixed: line starts with sentinel?}
  J -->|YES| K[Parse exit code + return full output]
```

If you apply A+C (anchored sentinel detection + proper stream buffering), `run` will stop returning `echo "` fragments and will reliably wait for the actual sentinel output line.

## Resolution

Implemented the fixes described above:

- `RingBuffer.append` now keeps a partial tail between PTY reads, joins fragments around newline boundaries, and only enqueues complete lines so a sentinel can never be split across read chunks.
- `SilcSession.run_command` strips ANSI/OSC noise, skips prompt-echo lines (using `ShellInfo.prompt_pattern`), and only accepts sentinel matches anchored at the start of a line (`__SILC_DONE_<id>__:<exit>`), returning the cleaned output once the completion line appears.
- Added a regression simulating prompt/progress output to `tests/test_session.py` so we keep the real command output while ignoring the echoed prompt before the sentinel.

## Manual verification

- `python main.py run 20000 "whoami"` now completes immediately and `python main.py out 20000` shows `whoami` plus the sentinel line rather than the prompt fragments.



[considered done]