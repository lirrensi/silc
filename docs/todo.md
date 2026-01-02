[?] create tests that clearly run entire process of open , type in, close shell
    1️⃣ tests/test_new_process.py – basic sanity check (start → run → in → close)  
    2️⃣ tests/process_test.py – uses a free‑port helper and explicit wait for the server  
    3️⃣ tests/integration_test.py – adds a short sleep and checks each step’s return code  
    4️⃣ tests/manual_flow.py – demonstrates the same flow with ls -l and echo  
    5️⃣ tests/full_process_manual.py – runs the complete open‑type‑close cycle with richer output  
    6️⃣ tests/test_full_workflow.py – final end‑to‑end script that ties everything together 
=> more tests for api functionality! and daemon also!

[ ] add input lock for streaming commands to enforce exclusive input


[x] - start should create persistent sessions, run in background;
=> detached process even with python main.py <cmd>
- add new `shutdown` that `close` all existing shells, `killall` does same + parent process
- ./silc should start keeping all sessions right at creation
=> daemon is still casing a trillion issues;

[x] see if possible to improve sentinel by NOT including it in outputs at all
- so it technically present in raw right buffer but `out` + `run` would skip it from outputs/
- want: after run command done: - strip sentinel string from ringbuffer so we dont see it when `out`


Progress => bringing to production v 0.1
[x] in/out/run mostly 90% ok, need testing interactive;
[x] daemon + server appears ok

[?] fix TUI so it works and behaves like a real shell: input + output + interactive + what else;
    [x] TUI not rerenders from buffer -> rendered as one would see!
    [x] input from TUI appears to have inputting continuos typing and control characters!
        => this is a long issue, possibly would be solved with /out filtering
    [ ] ensure TUI works at same time as a regular IN - expect to see realtime how it executes
    [ ] check RUN locks when TUI + api work at same time;

[ ] polish web app - that is our main TUI replacement for now;

[?] create exe build.
    [x] create simple system install => scripts to install into bash/pwsh profile;
        => maybe use pipx instead?
    [x] create pipx install that can install tool from repo;

[ ] normalizing newlines
/in always nukes whatever newline + adds platform specific
in "ls" => adds newlines
in "" => newliens === enter
input in web should behave exaclty same - must not add own newlines, server strips and adds
unless ?nonewline

but in web also commands line ctrlD SEND RAW INPUT WITHOUT NEWLINES, so it does not break anything


Progress:
- api 95%
- TUI ~50%, breaky
- webApp ~90%?
- daemon ~90%, need testing for crashes
- install scripts - to be tested 