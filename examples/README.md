# SILC Examples

This directory contains real-world examples of using SILC in various scenarios.

## Examples

### 1. AI/LLM Integration
**File:** `llm_integration.py`

Demonstrates how to integrate SILC with OpenAI's GPT-4 to create an AI agent that can execute shell commands.

**Use case:** Building AI-powered automation tools, intelligent DevOps assistants, or autonomous system management.

**Features:**
- AI decides what commands to run based on natural language
- Executes commands via SILC HTTP API
- Returns results to AI for further processing

**Run it:**
```bash
# Start SILC first
silc start

# Install dependencies
pip install openai requests

# Run the example
python examples/llm_integration.py
```

---

### 2. CI/CD Integration
**File:** `github_actions.yml`

Shows how to use SILC in GitHub Actions for deployment and testing.

**Use case:** Automating deployment pipelines, running tests in isolated environments, CI/CD workflows.

**Features:**
- Starts SILC daemon in CI environment
- Executes deployment scripts via HTTP API
- Runs tests and captures output
- Graceful cleanup

**Use it:**
```yaml
# Add to your .github/workflows/deploy.yml
name: Deploy with SILC
on: [push]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install SILC
        run: pip install -e .
      - name: Start SILC
        run: silc start
      - name: Deploy
        run: curl -X POST http://localhost:20000/run -d "./deploy.sh"
```

---

### 3. Monitoring Dashboard
**File:** `monitoring_dashboard.html`

A web-based dashboard for monitoring SILC sessions in real-time.

**Use case:** Operations dashboards, system monitoring, team collaboration, remote shell access.

**Features:**
- Real-time terminal output via WebSocket
- Execute commands from web interface
- Session status monitoring
- Multiple session support
- Beautiful dark theme UI

**Run it:**
```bash
# Start SILC
silc start

# Open the dashboard in your browser
open examples/monitoring_dashboard.html  # macOS
xdg-open examples/monitoring_dashboard.html  # Linux
start examples/monitoring_dashboard.html  # Windows
```

---

### 4. Python Integration
**File:** `python_integration.py`

Simple Python client for SILC's HTTP API with comprehensive examples.

**Use case:** Building custom tools, automation scripts, monitoring applications, integrations with other services.

**Features:**
- Clean Python API wrapper
- Error handling
- Multiple examples:
  - Basic command execution
  - File operations
  - System monitoring
  - Long-running process monitoring
  - Error handling
  - Session management

**Run it:**
```bash
# Start SILC first
silc start

# Install dependencies
pip install requests

# Run the examples
python examples/python_integration.py
```

---

## Quick Start with Examples

### Prerequisites
1. SILC installed and running
2. Python 3.12+
3. Required dependencies for each example

### Running Examples

1. **Start SILC:**
   ```bash
   silc start
   ```

2. **Choose an example:**
   ```bash
   # Python integration
   python examples/python_integration.py

   # LLM integration (requires OpenAI API key)
   export OPENAI_API_KEY="your-key-here"
   python examples/llm_integration.py

   # Monitoring dashboard
   open examples/monitoring_dashboard.html
   ```

---

## Creating Your Own Examples

### Basic Pattern

```python
import requests

# Connect to SILC
SILC_URL = "http://localhost:20000"

# Run a command
response = requests.post(f"{SILC_URL}/run", json={"command": "ls -la"})
result = response.json()

print(result["output"])
```

### WebSocket Pattern

```javascript
// Connect to SILC WebSocket
const ws = new WebSocket('ws://localhost:20000/ws');

// Receive real-time output
ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(data.data);
};

// Send input
ws.send(JSON.stringify({
    event: "type",
    text: "ls -la"
}));
```

---

## Common Use Cases

### 1. Automated Backups
```python
# Run backup script
response = requests.post(
    "http://localhost:20000/run",
    json={"command": "./backup.sh"}
)
```

### 2. Log Monitoring
```python
# Tail log file
response = requests.post(
    "http://localhost:20000/run",
    json={"command": "tail -f /var/log/app.log"}
)
```

### 3. System Health Checks
```python
# Check system health
commands = [
    "df -h",
    "free -m",
    "uptime"
]

for cmd in commands:
    response = requests.post(
        "http://localhost:20000/run",
        json={"command": cmd}
    )
    print(response.json()["output"])
```

### 4. Deployment Automation
```python
# Deploy application
steps = [
    "git pull origin main",
    "npm install",
    "npm run build",
    "systemctl restart myapp"
]

for step in steps:
    response = requests.post(
        "http://localhost:20000/run",
        json={"command": step}
    )
    if response.json()["exit_code"] != 0:
        print(f"Step failed: {step}")
        break
```

---

## Contributing Examples

Have a great example? We'd love to add it!

1. Create a new file in this directory
2. Add clear documentation
3. Include usage instructions
4. Submit a pull request

**Example template:**
```python
"""
Example: [Your Example Title]

Description of what this example demonstrates.

Use case: When to use this example

Requirements:
- List of dependencies

Run it:
- Instructions
"""

# Your code here
```

---

## Need Help?

- 📖 [Documentation](../docs/)
- 💬 [GitHub Discussions](https://github.com/lirrensi/silc/discussions)
- 🐛 [Issue Tracker](https://github.com/lirrensi/silc/issues)

---

**Happy coding! 🚀**
