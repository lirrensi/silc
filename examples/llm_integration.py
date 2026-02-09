"""
Example: Using SILC with OpenAI's GPT-4

This example demonstrates how an AI agent can use SILC to execute
shell commands and read output, enabling powerful automation capabilities.

Requirements:
- pip install openai requests
- SILC daemon running: silc start
"""

import openai
import requests
import json
from typing import Dict, Any


class SILCAgent:
    """AI Agent that can execute shell commands via SILC."""

    def __init__(self, silc_port: int = 20000, openai_api_key: str = None):
        """
        Initialize the SILC Agent.

        Args:
            silc_port: Port of the SILC session
            openai_api_key: OpenAI API key (or set OPENAI_API_KEY env var)
        """
        self.silc_port = silc_port
        self.silc_url = f"http://localhost:{silc_port}"
        self.client = openai.OpenAI(api_key=openai_api_key)

    def execute_command(self, command: str) -> Dict[str, Any]:
        """
        Execute a shell command via SILC API.

        Args:
            command: Shell command to execute

        Returns:
            Dictionary with output, exit_code, and status
        """
        response = requests.post(f"{self.silc_url}/run", json={"command": command})
        return response.json()

    def get_output(self, lines: int = 100) -> str:
        """
        Get the latest output from the session.

        Args:
            lines: Number of lines to fetch

        Returns:
            Output string
        """
        response = requests.get(f"{self.silc_url}/out?lines={lines}")
        return response.json()["output"]

    def think_and_execute(self, task: str) -> Dict[str, Any]:
        """
        Let the AI decide what command to run, then execute it.

        Args:
            task: Natural language description of what to do

        Returns:
            Result of command execution
        """
        # Step 1: AI decides what command to run
        print(f"🤖 AI is thinking about: {task}")

        system_prompt = """You are a helpful assistant that converts natural language tasks into shell commands.
Return ONLY the command, no explanation or extra text.
Use common Unix/Linux commands."""

        response = self.client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": task},
            ],
            temperature=0,
        )

        command = response.choices[0].message.content.strip()
        print(f"🤖 AI decided to run: {command}")

        # Step 2: Execute the command
        result = self.execute_command(command)

        # Step 3: Return results
        return {
            "task": task,
            "command": command,
            "output": result.get("output", ""),
            "exit_code": result.get("exit_code", -1),
            "status": result.get("status", "error"),
        }


def main():
    """Demonstrate SILC Agent capabilities."""

    # Initialize agent
    agent = SILCAgent(silc_port=20000)

    print("=" * 60)
    print("SILC AI Agent Demo")
    print("=" * 60)
    print()

    # Example 1: Simple file listing
    print("Example 1: List Python files in current directory")
    print("-" * 60)
    result = agent.think_and_execute("List all Python files in the current directory")
    print(f"Output:\n{result['output']}")
    print()

    # Example 2: Check disk usage
    print("Example 2: Check disk usage")
    print("-" * 60)
    result = agent.think_and_execute("Show disk usage for all mounted filesystems")
    print(f"Output:\n{result['output']}")
    print()

    # Example 3: Find large files
    print("Example 3: Find files larger than 10MB in current directory")
    print("-" * 60)
    result = agent.think_and_execute("Find files larger than 10MB in current directory")
    print(f"Output:\n{result['output']}")
    print()

    # Example 4: Check running processes
    print("Example 4: Show top 5 processes by CPU usage")
    print("-" * 60)
    result = agent.think_and_execute("Show top 5 processes by CPU usage")
    print(f"Output:\n{result['output']}")
    print()

    # Example 5: Multi-step task
    print("Example 5: Create a directory and add a file")
    print("-" * 60)
    result = agent.think_and_execute(
        "Create a directory called 'test_dir' and add a README file"
    )
    print(f"Output:\n{result['output']}")
    print()

    print("=" * 60)
    print("Demo complete!")
    print("=" * 60)


if __name__ == "__main__":
    # Make sure SILC is running first
    try:
        response = requests.get("http://localhost:20000/status")
        if response.status_code == 200:
            print("✓ SILC is running on port 20000")
            print()
            main()
        else:
            print("✗ SILC is not responding correctly")
            print("Start SILC with: silc start")
    except requests.exceptions.ConnectionError:
        print("✗ SILC is not running")
        print("Start SILC with: silc start")
