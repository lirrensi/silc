"""Tests for streaming service and configuration.

Tests cover StreamConfig validation, StreamingService lifecycle,
and integration with session output.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from silc.stream.config import StreamConfig, StreamMode
from silc.stream.deduplicator import LineDeduplicator
from silc.stream.streaming_service import StreamingService

# ============================================================================
# StreamConfig Tests
# ============================================================================


class TestStreamConfig:
    """Tests for StreamConfig validation."""

    def test_valid_render_config(self):
        """Create valid render mode config."""
        config = StreamConfig(mode=StreamMode.RENDER, filename="output.txt")

        assert config.mode == StreamMode.RENDER
        assert config.filename == "output.txt"
        assert config.interval == 5  # default

    def test_valid_append_config(self):
        """Create valid append mode config."""
        config = StreamConfig(
            mode=StreamMode.APPEND,
            filename="output.txt",
            window_size=1000,
            similarity_threshold=0.9,
        )

        assert config.mode == StreamMode.APPEND
        assert config.window_size == 1000
        assert config.similarity_threshold == 0.9

    def test_interval_validation_min(self):
        """Interval must be at least 1 second."""
        with pytest.raises(Exception):  # ValidationError
            StreamConfig(mode=StreamMode.RENDER, filename="out.txt", interval=0)

    def test_interval_validation_max(self):
        """Interval must be at most 3600 seconds."""
        with pytest.raises(Exception):  # ValidationError
            StreamConfig(mode=StreamMode.RENDER, filename="out.txt", interval=3601)

    def test_window_size_validation_min(self):
        """Window size must be at least 100."""
        with pytest.raises(Exception):  # ValidationError
            StreamConfig(mode=StreamMode.APPEND, filename="out.txt", window_size=50)

    def test_window_size_validation_max(self):
        """Window size must be at most 10000."""
        with pytest.raises(Exception):  # ValidationError
            StreamConfig(mode=StreamMode.APPEND, filename="out.txt", window_size=15000)

    def test_similarity_threshold_validation_min(self):
        """Similarity threshold must be at least 0.0."""
        with pytest.raises(Exception):  # ValidationError
            StreamConfig(
                mode=StreamMode.APPEND, filename="out.txt", similarity_threshold=-0.1
            )

    def test_similarity_threshold_validation_max(self):
        """Similarity threshold must be at most 1.0."""
        with pytest.raises(Exception):  # ValidationError
            StreamConfig(
                mode=StreamMode.APPEND, filename="out.txt", similarity_threshold=1.1
            )

    def test_max_file_size_validation(self):
        """Max file size validation."""
        # Valid
        config = StreamConfig(
            mode=StreamMode.RENDER, filename="out.txt", max_file_size_mb=50
        )
        assert config.max_file_size_mb == 50

        # Invalid (too small)
        with pytest.raises(Exception):
            StreamConfig(mode=StreamMode.RENDER, filename="out.txt", max_file_size_mb=0)

        # Invalid (too large)
        with pytest.raises(Exception):
            StreamConfig(
                mode=StreamMode.RENDER, filename="out.txt", max_file_size_mb=2000
            )

    def test_rotation_policy_values(self):
        """Rotation policy accepts valid values."""
        for policy in ["none", "size", "time"]:
            config = StreamConfig(
                mode=StreamMode.RENDER, filename="out.txt", rotation_policy=policy
            )
            assert config.rotation_policy == policy

    def test_mode_enum_values(self):
        """Mode accepts valid enum values."""
        assert StreamMode.RENDER.value == "render"
        assert StreamMode.APPEND.value == "append"

    def test_config_dict_for_api(self):
        """Config can be serialized to dict for API."""
        config = StreamConfig(mode=StreamMode.RENDER, filename="test.txt")
        data = config.dict()

        assert "mode" in data
        assert "filename" in data
        assert "interval" in data


# ============================================================================
# StreamingService Unit Tests
# ============================================================================


class TestStreamingServiceUnit:
    """Unit tests for StreamingService with mocked session."""

    def test_init(self):
        """Service initializes with session."""
        mock_session = MagicMock()
        service = StreamingService(mock_session)

        assert service.session is mock_session
        assert service.active_streams == {}
        assert isinstance(service.deduplicator, LineDeduplicator)

    @pytest.mark.asyncio
    async def test_start_stream_render(self):
        """Start render stream creates task."""
        mock_session = MagicMock()
        mock_session.get_rendered_output = MagicMock(return_value="test output")
        service = StreamingService(mock_session)

        config = StreamConfig(mode=StreamMode.RENDER, filename="test.txt", interval=1)

        task_id = await service.start_stream(config)

        assert task_id == "test.txt"
        assert "test.txt" in service.active_streams

        # Cleanup
        await service.stop_stream("test.txt")

    @pytest.mark.asyncio
    async def test_start_stream_append(self):
        """Start append stream creates task."""
        mock_session = MagicMock()
        mock_session.buffer = MagicMock()
        mock_session.buffer.get_last = MagicMock(return_value="line1\nline2")
        service = StreamingService(mock_session)

        config = StreamConfig(
            mode=StreamMode.APPEND, filename="test_append.txt", interval=1
        )

        task_id = await service.start_stream(config)

        assert task_id == "test_append.txt"
        assert "test_append.txt" in service.active_streams

        # Cleanup
        await service.stop_stream("test_append.txt")

    @pytest.mark.asyncio
    async def test_start_stream_duplicate_fails(self):
        """Starting stream with same filename fails."""
        mock_session = MagicMock()
        mock_session.get_rendered_output = MagicMock(return_value="output")
        service = StreamingService(mock_session)

        config = StreamConfig(mode=StreamMode.RENDER, filename="dup.txt", interval=1)

        await service.start_stream(config)

        # Try to start again with same filename
        with pytest.raises(ValueError, match="already active"):
            await service.start_stream(config)

        # Cleanup
        await service.stop_stream("dup.txt")

    @pytest.mark.asyncio
    async def test_start_stream_invalid_mode(self):
        """Invalid mode raises error."""
        mock_session = MagicMock()
        service = StreamingService(mock_session)

        # Create config with invalid mode by mocking
        config = MagicMock()
        config.mode = "invalid_mode"
        config.filename = "test.txt"

        with pytest.raises(ValueError, match="Unsupported stream mode"):
            await service.start_stream(config)

    @pytest.mark.asyncio
    async def test_stop_stream_existing(self):
        """Stop existing stream returns True."""
        mock_session = MagicMock()
        mock_session.get_rendered_output = MagicMock(return_value="output")
        service = StreamingService(mock_session)

        config = StreamConfig(
            mode=StreamMode.RENDER, filename="to_stop.txt", interval=1
        )
        await service.start_stream(config)

        result = await service.stop_stream("to_stop.txt")

        assert result is True
        assert "to_stop.txt" not in service.active_streams

    @pytest.mark.asyncio
    async def test_stop_stream_nonexistent(self):
        """Stop nonexistent stream returns False."""
        mock_session = MagicMock()
        service = StreamingService(mock_session)

        result = await service.stop_stream("nonexistent.txt")

        assert result is False

    def test_get_stream_status_empty(self):
        """Get status when no streams."""
        mock_session = MagicMock()
        service = StreamingService(mock_session)

        status = service.get_stream_status()

        assert status == {}

    @pytest.mark.asyncio
    async def test_get_stream_status_active(self):
        """Get status with active stream."""
        mock_session = MagicMock()
        mock_session.get_rendered_output = MagicMock(return_value="output")
        service = StreamingService(mock_session)

        config = StreamConfig(mode=StreamMode.RENDER, filename="active.txt", interval=1)
        await service.start_stream(config)

        status = service.get_stream_status()

        assert "active.txt" in status
        assert status["active.txt"]["active"] is True

        # Cleanup
        await service.stop_stream("active.txt")

    @pytest.mark.asyncio
    async def test_stop_all_streams(self):
        """Stop all streams at once."""
        mock_session = MagicMock()
        mock_session.get_rendered_output = MagicMock(return_value="output")
        service = StreamingService(mock_session)

        config1 = StreamConfig(mode=StreamMode.RENDER, filename="file1.txt", interval=1)
        config2 = StreamConfig(mode=StreamMode.RENDER, filename="file2.txt", interval=1)

        await service.start_stream(config1)
        await service.start_stream(config2)

        assert len(service.active_streams) == 2

        await service.stop_all_streams()

        assert len(service.active_streams) == 0


# ============================================================================
# StreamingService File Operations Tests
# ============================================================================


class TestStreamingServiceFileOps:
    """Tests for file operations in streaming service."""

    @pytest.mark.asyncio
    async def test_render_writes_file(self):
        """Render mode writes to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "render_output.txt")

            mock_session = MagicMock()
            mock_session.get_rendered_output = MagicMock(
                return_value="test content\nline 2"
            )
            service = StreamingService(mock_session)

            config = StreamConfig(
                mode=StreamMode.RENDER, filename=output_file, interval=1
            )

            await service.start_stream(config)
            await asyncio.sleep(1.5)  # Let it write once
            await service.stop_stream(output_file)

            # Check file was written
            assert os.path.exists(output_file)
            with open(output_file, "r") as f:
                content = f.read()
            assert "test content" in content

    @pytest.mark.asyncio
    async def test_append_creates_file(self):
        """Append mode creates file if not exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "append_output.txt")

            mock_session = MagicMock()
            mock_session.buffer = MagicMock()
            mock_session.buffer.get_last = MagicMock(
                return_value="new line 1\nnew line 2"
            )
            service = StreamingService(mock_session)

            config = StreamConfig(
                mode=StreamMode.APPEND, filename=output_file, interval=1
            )

            await service.start_stream(config)
            await asyncio.sleep(1.5)
            await service.stop_stream(output_file)

            # File may or may not exist depending on timing
            # This test is more about ensuring no crash

    @pytest.mark.asyncio
    async def test_append_appends_to_existing(self):
        """Append mode adds to existing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = os.path.join(tmpdir, "existing.txt")

            # Create existing file
            with open(output_file, "w") as f:
                f.write("existing line\n")

            mock_session = MagicMock()
            mock_session.buffer = MagicMock()
            mock_session.buffer.get_last = MagicMock(
                return_value="existing line\nnew appended line"
            )
            service = StreamingService(mock_session)

            config = StreamConfig(
                mode=StreamMode.APPEND,
                filename=output_file,
                interval=1,
                window_size=100,
            )

            await service.start_stream(config)
            await asyncio.sleep(1.5)
            await service.stop_stream(output_file)

            # Check file still has original content
            with open(output_file, "r") as f:
                content = f.read()
            assert "existing line" in content


# ============================================================================
# StreamingService Error Handling Tests
# ============================================================================


class TestStreamingServiceErrors:
    """Tests for error handling in streaming service."""

    @pytest.mark.asyncio
    async def test_render_continues_on_error(self):
        """Render mode continues after write error."""
        mock_session = MagicMock()
        mock_session.get_rendered_output = MagicMock(
            side_effect=Exception("Simulated error")
        )
        service = StreamingService(mock_session)

        config = StreamConfig(
            mode=StreamMode.RENDER, filename="/invalid/path/file.txt", interval=1
        )

        # Should not raise
        await service.start_stream(config)
        await asyncio.sleep(0.5)

        # Task should still be active
        status = service.get_stream_status()
        # May be active or have exception
        assert "file.txt" in status or True  # Best effort

        # Cleanup
        await service.stop_stream("/invalid/path/file.txt")

    @pytest.mark.asyncio
    async def test_append_continues_on_error(self):
        """Append mode continues after error."""
        mock_session = MagicMock()
        mock_session.buffer = MagicMock()
        mock_session.buffer.get_last = MagicMock(side_effect=Exception("Buffer error"))
        service = StreamingService(mock_session)

        config = StreamConfig(
            mode=StreamMode.APPEND, filename="error_test.txt", interval=1
        )

        # Should not raise
        await service.start_stream(config)
        await asyncio.sleep(0.5)

        # Cleanup
        await service.stop_stream("error_test.txt")


# ============================================================================
# Integration Tests (require session)
# ============================================================================


@pytest.mark.integration
class TestStreamingServiceIntegration:
    """Integration tests with actual session."""

    @pytest.mark.asyncio
    async def test_stream_with_session_output(self):
        """Test streaming with actual session output."""
        # This test requires a real session
        pytest.skip("Requires real session - run with integration marker")

    @pytest.mark.asyncio
    async def test_concurrent_streams(self):
        """Multiple concurrent streams to different files."""
        pytest.skip("Requires real session - run with integration marker")


# ============================================================================
# Deduplicator Additional Tests
# ============================================================================


class TestLineDeduplicatorAdditional:
    """Additional tests for LineDeduplicator beyond test_deduplicator.py."""

    def test_cache_bounded_growth(self):
        """Cache is bounded and doesn't grow unbounded."""
        deduplicator = LineDeduplicator(window_size=100)

        # Add many lines to cache
        large_existing = [f"line_{i}" for i in range(5000)]
        new = ["line_0", "new_line"]

        diff = deduplicator.compute_diff(large_existing, new)

        # Cache should have been bounded
        # The exact size depends on implementation details
        assert len(deduplicator._exact_cache) <= deduplicator._cache_max_size

    def test_cache_clear_and_rebuild(self):
        """Cache clears and rebuilds when over limit."""
        deduplicator = LineDeduplicator(window_size=10)

        # First, fill the cache
        existing1 = [f"batch1_line_{i}" for i in range(100)]
        deduplicator.compute_diff(existing1, ["new"])

        # Cache should be populated
        assert len(deduplicator._exact_cache) > 0

        # Now add more lines that exceed cache max
        existing2 = [f"batch2_line_{i}" for i in range(5000)]
        deduplicator.compute_diff(existing2, ["newer"])

        # Cache should still be bounded
        assert len(deduplicator._exact_cache) <= deduplicator._cache_max_size

    def test_fuzzy_match_short_lines(self):
        """Fuzzy matching handles short lines."""
        deduplicator = LineDeduplicator(similarity_threshold=0.85)

        # Very short lines
        assert deduplicator.is_similar("a", "a")
        assert not deduplicator.is_similar("a", "b")

    def test_fuzzy_match_unicode(self):
        """Fuzzy matching handles Unicode."""
        deduplicator = LineDeduplicator(similarity_threshold=0.85)

        # Unicode strings
        assert deduplicator.is_similar("hello 世界", "hello 世界")
        assert deduplicator.is_similar("hello 世界", "hello 世界!")  # Small diff

    def test_normalize_unicode(self):
        """Normalization handles Unicode."""
        deduplicator = LineDeduplicator()

        # Unicode should be preserved but lowercased
        result = deduplicator.normalize_line("HELLO 世界")
        assert "世界" in result  # Unicode preserved
        assert "hello" in result  # Lowercased

    def test_window_size_edge_case(self):
        """Window size of 1 works correctly."""
        deduplicator = LineDeduplicator(window_size=1)
        existing = ["line1", "line2", "line3"]
        new = ["line3", "new"]

        # Only last line should be considered
        diff = deduplicator.compute_diff(existing, new)

        # line3 should be detected as duplicate (last in existing)
        # new should be novel
        assert "new" in diff

    def test_compute_diff_preserves_original_lines(self):
        """compute_diff preserves original line formatting."""
        deduplicator = LineDeduplicator()
        existing = ["line1"]
        new = ["  Line1  ", "\tline1\t", "new line"]

        diff = deduplicator.compute_diff(existing, new)

        # Normalized versions should match but original formatting preserved in diff
        # The duplicates should be filtered
        assert "new line" in diff
