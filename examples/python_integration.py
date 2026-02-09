"""
Example: Simple Python Integration with SILC

This example demonstrates basic Python integration with SILC's HTTP API.
Perfect for automation scripts, monitoring tools, and custom applications.

Requirements:
- pip install requests
- SILC daemon running: silc start
"""

import requests
import time
from typing import Dict, Any, Optional


class SILCClient:
    """Simple Python client for SILC HTTP API."""

    def __init__(self, host: str = "localhost", port: int = 20000):
        """
        Initialize SILC client.

        Args:
            host: SILC host (default: localhost)
            port: SILC session port (default: 20000)
        """
        self.base_url = f"http://{host}:{port}"

    def run_command(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Execute a shell command.

        Args:
            command: Shell command to execute
            timeout: Command timeout in seconds

        Returns:
            Dictionary with output, exit_code, and status
        """
        response = requests.post(
            f"{self.base_url}/run", json={"command": command, "timeout": timeout}
        )
        response.raise_for_status()
        return response.json()

    def get_output(self, lines: int = 100) -> str:
        """
        Get the latest output from the session.

        Args:
            lines: Number of lines to fetch

        Returns:
            Output string
        """
        response = requests.get(f"{self.base_url}/out?lines={lines}")
        response.raise_for_status()
        return response.json()["output"]

    def get_status(self) -> Dict[str, Any]:
        """
        Get session status.

        Returns:
            Dictionary with session status information
        """
        response = requests.get(f"{self.base_url}/status")
        response.raise_for_status()
        return response.json()

    def send_input(self, text: str) -> Dict[str, Any]:
        """
        Send raw input to the session.

        Args:
            text: Text to send

        Returns:
            Response dictionary
        """
        response = requests.post(f"{self.base_url}/in", data=text)
        response.raise_for_status()
        return response.json()

    def interrupt(self) -> Dict[str, Any]:
        """
        Send Ctrl+C to interrupt running command.

        Returns:
            Response dictionary
        """
        response = requests.post(f"{self.base_url}/interrupt")
        response.raise_for_status()
        return response.json()

    def clear_buffer(self) -> Dict[str, Any]:
        """
        Clear the output buffer.

        Returns:
            Response dictionary
        """
        response = requests.post(f"{self.base_url}/clear")
        response.raise_for_status()
        return response.json()

    def resize_terminal(self, rows: int, cols: int) -> Dict[str, Any]:
        """
        Resize the terminal.

        Args:
            rows: Number of rows
            cols: Number of columns

        Returns:
            Response dictionary
        """
        response = requests.post(
            f"{self.base_url}/resize", json={"rows": rows, "cols": cols}
        )
        response.raise_for_status()
        return response.json()

    def close(self) -> Dict[str, Any]:
        """
        Gracefully close the session.

        Returns:
            Response dictionary
        """
        response = requests.post(f"{self.base_url}/close")
        response.raise_for_status()
        return response.json()


def example_1_basic_commands():
    """Example 1: Basic command execution."""
    print("=" * 60)
    print("Example 1: Basic Commands")
    print("=" * 60)

    client = SILCClient(port=20000)

    # Run a simple command
    result = client.run_command("echo 'Hello from SILC!'")
    print(f"Command: echo 'Hello from SILC!'")
    print(f"Output: {result['output']}")
    print(f"Exit Code: {result['exit_code']}")
    print()

    # Run multiple commands
    commands = ["pwd", "ls -la", "date"]

    for cmd in commands:
        result = client.run_command(cmd)
        print(f"Command: {cmd}")
        print(f"Output: {result['output'][:100]}...")  # Show first 100 chars
        print()


def example_2_file_operations():
    """Example 2: File operations."""
    print("=" * 60)
    print("Example 2: File Operations")
    print("=" * 60)

    client = SILCClient(port=20000)

    # Create a directory
    client.run_command("mkdir -p test_silc_dir")
    print("✓ Created directory: test_silc_dir")

    # Create a file
    client.run_command("echo 'SILC test file' > test_silc_dir/test.txt")
    print("✓ Created file: test_silc_dir/test.txt")

    # Read the file
    result = client.run_command("cat test_silc_dir/test.txt")
    print(f"File contents: {result['output']}")

    # List directory
    result = client.run_command("ls -la test_silc_dir/")
    print(f"Directory listing:\n{result['output']}")

    # Cleanup
    client.run_command("rm -rf test_silc_dir")
    print("✓ Cleaned up test directory")
    print()


def example_3_monitoring():
    """Example 3: System monitoring."""
    print("=" * 60)
    print("Example 3: System Monitoring")
    print("=" * 60)

    client = SILCClient(port=20000)

    # Check disk usage
    result = client.run_command("df -h")
    print("Disk Usage:")
    print(result["output"])
    print()

    # Check memory usage
    result = client.run_command("free -h")
    print("Memory Usage:")
    print(result["output"])
    print()

    # Check CPU usage
    result = client.run_command("top -bn1 | head -n 10")
    print("CPU Usage (top 10 lines):")
    print(result["output"])
    print()


def example_4_long_running_process():
    """Example 4: Long-running process monitoring."""
    print("=" * 60)
    print("Example 4: Long-Running Process")
    print("=" * 60)

    client = SILCClient(port=20000)

    # Start a long-running process in background
    print("Starting long-running process...")
    client.run_command("nohup sleep 10 > /dev/null 2>&1 &")

    # Monitor the process
    for i in range(5):
        result = client.run_command("ps aux | grep sleep | grep -v grep")
        if result["output"]:
            print(f"Check {i + 1}: Process is running")
        else:
            print(f"Check {i + 1}: Process has completed")
        time.sleep(2)

    print()


def example_5_error_handling():
    """Example 5: Error handling."""
    print("=" * 60)
    print("Example 5: Error Handling")
    print("=" * 60)

    client = SILCClient(port=20000)

    # Try to run a command that will fail
    try:
        result = client.run_command("ls /nonexistent_directory")
        print(f"Command failed with exit code: {result['exit_code']}")
        print(f"Error output: {result['output']}")
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

    # Run a command that succeeds
    try:
        result = client.run_command("ls /tmp")
        print(f"Command succeeded with exit code: {result['exit_code']}")
        print(f"Output: {result['output'][:100]}...")
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")

    print()


def example_6_session_management():
    """Example 6: Session management."""
    print("=" * 60)
    print("Example 6: Session Management")
    print("=" * 60)

    client = SILCClient(port=20000)

    # Get session status
    status = client.get_status()
    print(f"Session Status:")
    print(f"  Alive: {status['alive']}")
    print(f"  Shell: {status['shell']}")
    print(f"  PID: {status['pid']}")
    print(f"  Idle Time: {status['idle_time']:.2f}s")
    print()

    # Resize terminal
    client.resize_terminal(rows=40, cols=120)
    print("✓ Resized terminal to 40x120")
    print()

    # Clear buffer
    client.clear_buffer()
    print("✓ Cleared output buffer")
    print()


def main():
    """Run all examples."""
    print("\n" + "=" * 60)
    print("SILC Python Integration Examples")
    print("=" * 60 + "\n")

    try:
        # Check if SILC is running
        client = SILCClient(port=20000)
        status = client.get_status()
        print(f"✓ SILC is running on port 20000")
        print(f"✓ Session is alive: {status['alive']}")
        print()

        # Run examples
        example_1_basic_commands()
        example_2_file_operations()
        example_3_monitoring()
        example_4_long_running_process()
        example_5_error_handling()
        example_6_session_management()

        print("=" * 60)
        print("All examples completed successfully!")
        print("=" * 60)

    except requests.exceptions.ConnectionError:
        print("✗ SILC is not running")
        print("Start SILC with: silc start")
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    main()
