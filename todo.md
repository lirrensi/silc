[?] create tests that clearly run entire process of open , type in, close shell
    1️⃣ tests/test_new_process.py – basic sanity check (start → run → in → close)  
    2️⃣ tests/process_test.py – uses a free‑port helper and explicit wait for the server  
    3️⃣ tests/integration_test.py – adds a short sleep and checks each step’s return code  
    4️⃣ tests/manual_flow.py – demonstrates the same flow with ls -l and echo  
    5️⃣ tests/full_process_manual.py – runs the complete open‑type‑close cycle with richer output  
    6️⃣ tests/test_full_workflow.py – final end‑to‑end script that ties everything together 


[x] cutoff all pypty and replace with correct doc.
[?] implement ShellInfo.get_sentinel_command method for run command sentinel
[ ] add input lock for streaming commands to enforce exclusive input
[ ] fix RingBuffer cursor handling after clear operation

[?] make idle garbage collection more aggressive (e.g., shorter interval)
    => maybe 30 min default
    => check how we detect activity! - should be: any command/api call | has subprocess | has TUI opened/connected
[?] ensure TUI forwards terminal resize events to PTY
    => needed? as pty is engine, and tui would be just for rendering;
    => decided not worth it;


[ ] pyz package for quick testing
[ ] pyinstall for entire app for both;


cmd> ./.venv-win/Scripts/activate.ps1
