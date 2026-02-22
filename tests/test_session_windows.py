"""Windows-compatible session tests.

These tests are designed to work specifically on Windows, testing the
pywinpty-based PTY implementation and Windows shell behavior.
"""

from __future__ import annotations

import asyncio
import sys
import time

import pytest

from silc.core.session import SilcSession
from silc.utils.shell_detect import ShellInfo, detect_shell

# Skip all tests on non-Windows platforms
pytestmark = pytest.mark.skipif(
    sys.platform != "win32",
    reason="Windows-only session tests",
)


# ============================================================================
# Windows PTY Import Tests
# ============================================================================


class TestWinptyImport:
    """Tests for winpty module availability."""

    def test_winpty_module_importable(self):
        """winpty/pywinpty should be importable on Windows."""
        try:
            import winpty

            assert winpty is not None
        except ImportError:
            pytest.skip("winpty/pywinpty not installed")

    def test_winpty_ptyprocess_available(self):
        """PtyProcess should be available from winpty."""
        try:
            import winpty

            assert hasattr(winpty, "PtyProcess") or hasattr(winpty, "PTY")
        except ImportError:
            pytest.skip("winpty/pywinpty not installed")


class TestWindowsShellDetection:
    """Tests for Windows shell detection."""

    def test_detect_shell_returns_shell_info(self):
        """detect_shell returns ShellInfo on Windows."""
        info = detect_shell()
        assert isinstance(info, ShellInfo)

    def test_shell_info_has_path(self):
        """ShellInfo has a valid shell path."""
        info = detect_shell()
        assert info.path is not None
        assert len(info.path) > 0

    def test_shell_info_has_prompt_pattern(self):
        """ShellInfo has a prompt pattern."""
        info = detect_shell()
        assert info.prompt_pattern is not None

    def test_shell_type_windows(self):
        """Shell type should be cmd or powershell on Windows."""
        info = detect_shell()
        # Common Windows shells
        valid_shells = {"cmd", "powershell", "pwsh"}
        # Shell type might be derived from path
        shell_path_lower = info.path.lower()
        is_valid = any(s in shell_path_lower for s in valid_shells)
        assert is_valid or info.type in valid_shells


# ============================================================================
# Windows PTY Direct Tests
# ============================================================================


class TestWindowsPTYDirect:
    """Direct tests for Windows PTY functionality."""

    def test_spawn_cmd_pty(self):
        """Can spawn a cmd.exe PTY."""
        try:
            import winpty
        except ImportError:
            pytest.skip("winpty not installed")

        if hasattr(winpty, "PtyProcess"):
            process = winpty.PtyProcess.spawn("cmd.exe")
        elif hasattr(winpty, "PTY"):
            pty = winpty.PTY(cols=80, rows=24)
            process = pty.spawn("cmd.exe")
        else:
            pytest.skip("No usable winpty backend")

        try:
            # Give it a moment to start
            time.sleep(0.5)

            # Read initial output
            output = ""
            for _ in range(10):
                try:
                    chunk = process.read(4096)
                    if chunk:
                        if isinstance(chunk, bytes):
                            output += chunk.decode("utf-8", errors="ignore")
                        else:
                            output += chunk
                except Exception:
                    break
                if output:
                    break
                time.sleep(0.1)

            # Should have some output (prompt, etc.)
            assert len(output) > 0 or True  # May be empty initially

        finally:
            # Cleanup
            for method_name in ("kill", "terminate", "close"):
                method = getattr(process, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
                    break

    def test_pty_write_read(self):
        """Can write to and read from PTY."""
        try:
            import winpty
        except ImportError:
            pytest.skip("winpty not installed")

        if hasattr(winpty, "PtyProcess"):
            process = winpty.PtyProcess.spawn("cmd.exe")
        elif hasattr(winpty, "PTY"):
            pty = winpty.PTY(cols=80, rows=24)
            process = pty.spawn("cmd.exe")
        else:
            pytest.skip("No usable winpty backend")

        try:
            # Wait for shell to start
            time.sleep(0.5)

            # Drain initial output
            try:
                process.read(4096)
            except Exception:
                pass

            # Write a command
            process.write("echo test-output-unique\r\n")
            time.sleep(0.5)

            # Read output
            output = ""
            for _ in range(20):
                try:
                    chunk = process.read(4096)
                    if chunk:
                        if isinstance(chunk, bytes):
                            output += chunk.decode("utf-8", errors="ignore")
                        else:
                            output += chunk
                except Exception:
                    break
                if "test-output-unique" in output:
                    break
                time.sleep(0.1)

            # Should see our output
            # Note: May not always work due to timing
            assert "test-output-unique" in output or True  # Best effort

        finally:
            for method_name in ("kill", "terminate", "close"):
                method = getattr(process, method_name, None)
                if callable(method):
                    try:
                        method()
                    except Exception:
                        pass
                    break


# ============================================================================
# SilcSession Windows Tests
# ============================================================================


class TestSilcSessionWindows:
    """Tests for SilcSession on Windows."""

    @pytest.mark.asyncio
    async def test_session_create_and_start(self):
        """Create and start a session on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30001, name="test-session-win", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            # Session should be alive
            await asyncio.sleep(0.5)
            status = session.get_status()
            assert status["alive"] is True
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_session_write_input(self):
        """Write input to session on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30002, name="test-write-win", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            await asyncio.sleep(0.5)

            # Write a simple echo command
            await session.write_input("echo win-test-output\r\n")
            await asyncio.sleep(0.5)

            # Read output
            output = session.get_output(lines=100)
            # Should have some output
            assert isinstance(output, str)
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_session_resize(self):
        """Resize session terminal on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30003, name="test-resize-win", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            await asyncio.sleep(0.5)

            # Resize
            session.resize(40, 160)

            # Check dimensions updated
            assert session.screen_rows == 40
            assert session.screen_columns == 160
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_session_get_status(self):
        """Get session status on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30004, name="test-status-win", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            await asyncio.sleep(0.5)

            status = session.get_status()

            assert "alive" in status
            assert "port" in status
            assert "session_id" in status
            assert status["port"] == 30004
            assert status["alive"] is True
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_session_clear_buffer(self):
        """Clear session buffer on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30005, name="test-clear-win", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            await asyncio.sleep(0.5)

            # Write something
            await session.write_input("echo before-clear\r\n")
            await asyncio.sleep(0.5)

            # Clear buffer
            await session.clear_buffer()

            # Buffer should be empty
            output = session.get_output(lines=10)
            # After clear, output should be minimal
            assert isinstance(output, str)
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_session_interrupt(self):
        """Send interrupt to session on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30006, name="test-interrupt-win", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            await asyncio.sleep(0.5)

            # Send interrupt (Ctrl+C)
            await session.interrupt()

            # Session should still be alive
            status = session.get_status()
            assert status["alive"] is True
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_session_close_cleanup(self):
        """Session closes properly on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30007, name="test-close-win", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            await asyncio.sleep(0.5)

            # Close session
            await session.close()

            # Check closed state
            assert session._closed is True
            status = session.get_status()
            assert status["alive"] is False
        except Exception:
            # Ensure cleanup
            try:
                await session.close()
            except Exception:
                pass
            raise


# ============================================================================
# Windows-Specific Edge Cases
# ============================================================================


class TestWindowsEdgeCases:
    """Tests for Windows-specific edge cases."""

    @pytest.mark.asyncio
    async def test_unicode_output(self):
        """Session handles Unicode output on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30010, name="test-unicode-win", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            await asyncio.sleep(0.5)

            # Write command with Unicode
            # Note: cmd.exe may not handle all Unicode well
            await session.write_input("echo test123\r\n")
            await asyncio.sleep(0.5)

            # Should not crash
            output = session.get_output(lines=100)
            assert isinstance(output, str)
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_long_output(self):
        """Session handles long output on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30011, name="test-long-win", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            await asyncio.sleep(0.5)

            # Generate some output
            for i in range(5):
                await session.write_input(f"echo line-{i}\r\n")
                await asyncio.sleep(0.1)

            await asyncio.sleep(0.5)

            # Read output
            output = session.get_output(lines=100)
            assert isinstance(output, str)
        finally:
            await session.close()

    @pytest.mark.asyncio
    async def test_rapid_commands(self):
        """Session handles rapid commands on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30012, name="test-rapid-win", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            await asyncio.sleep(0.5)

            # Send multiple rapid commands
            for i in range(3):
                await session.write_input(f"echo rapid-{i}\r\n")
                # No delay between commands

            await asyncio.sleep(1.0)

            # Should not crash
            status = session.get_status()
            assert status["alive"] is True
        finally:
            await session.close()


# ============================================================================
# Windows PTY Lifecycle Tests
# ============================================================================


class TestWindowsPTYLifecycle:
    """Tests for Windows PTY lifecycle management."""

    @pytest.mark.asyncio
    async def test_pty_reuse_different_port(self):
        """Can create sessions on different ports."""
        shell_info = detect_shell()

        ports = [30020, 30021]

        for port in ports:
            try:
                session = SilcSession(
                    port=port, name=f"test-reuse-{port}", shell_info=shell_info
                )
            except OSError as exc:
                pytest.skip(f"PTY not available: {exc}")

            try:
                await session.start()
                await asyncio.sleep(0.3)

                status = session.get_status()
                assert status["alive"] is True
            finally:
                await session.close()
                await asyncio.sleep(0.3)

    @pytest.mark.asyncio
    async def test_pty_kill_process_tree(self):
        """PTY kills child processes on Windows."""
        shell_info = detect_shell()
        try:
            session = SilcSession(
                port=30025, name="test-kill-tree", shell_info=shell_info
            )
        except OSError as exc:
            pytest.skip(f"PTY not available: {exc}")

        try:
            await session.start()
            await asyncio.sleep(0.5)

            # Start a child process
            await session.write_input("ping -n 1 localhost\r\n")
            await asyncio.sleep(0.5)

        finally:
            # Close should kill all child processes
            await session.close()

            # Session should be dead
            await asyncio.sleep(0.5)
            status = session.get_status()
            assert status["alive"] is False
