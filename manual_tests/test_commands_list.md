cmd> ./.venv-win/Scripts/activate.ps1

## CLI smoke tests (use the same port in every command)

cmd> python main.py start --port 20000
cmd> python main.py list
cmd> python main.py 20000 open         # launches Textual TUI
cmd> python main.py 20000 out          # fetch cleaned output
cmd> python main.py 20000 out 50      # fetch last 50 lines
cmd> python main.py 20000 in "echo hi"
cmd> python main.py 20000 run "whoami"
cmd> python main.py 20000 status

## Daemon management

cmd> python main.py shutdown           # graceful shutdown (closes all sessions)
cmd> python main.py killall            # force kill daemon and all sessions

## API sanity checks (switch to another window if TUI is open)

# Status / metadata
cmd> curl http://localhost:20000/status

# Output stream (cleaned by default)
cmd> curl http://localhost:20000/out
cmd> curl http://localhost:20000/out?lines=200

# Raw stream (ANSI/CRLF preserved)
cmd> curl "http://localhost:20000/raw?raw=true&lines=20"
cmd> curl http://localhost:20000/stream

# Send literal input (newline auto-appended unless ?nonewline=true)
cmd> curl.exe -X POST http://localhost:20000/in -d "ls"
cmd> curl.exe -X POST "http://localhost:20000/in?nonewline=true" -d "\x03"

# Run command (raw body or JSON accepted; waits for sentinel)
cmd> curl.exe -X POST http://localhost:20000/run -d "npm --version"
cmd> curl -X POST http://localhost:20000/run -H "Content-Type: application/json" \
       -d '{"command":"pwd","timeout":30}'

# Session control
cmd> curl -X POST http://localhost:20000/interrupt
cmd> curl -X POST http://localhost:20000/clear
cmd> curl -X POST http://localhost:20000/tui/activate
cmd> curl -X POST http://localhost:20000/tui/deactivate

# Shutdown helpers
cmd> curl -X POST http://localhost:20000/close
cmd> curl -X POST http://localhost:20000/kill
