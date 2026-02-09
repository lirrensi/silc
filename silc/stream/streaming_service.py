"""Streaming service for file output operations."""

import asyncio
import logging
import os
from typing import Any, Dict, Optional

import aiofiles

from silc.stream.config import StreamConfig, StreamMode
from silc.stream.deduplicator import LineDeduplicator

logger = logging.getLogger(__name__)


class StreamingService:
    """Manages streaming tasks for file output."""

    def __init__(self, session: Any):
        """Initialize streaming service.

        Args:
            session: Session instance for accessing output
        """
        self.session = session
        self.active_streams: Dict[str, asyncio.Task] = {}
        self.deduplicator = LineDeduplicator()

    async def start_stream(self, config: StreamConfig) -> str:
        """Start a new streaming task.

        Args:
            config: Streaming configuration

        Returns:
            Task ID for the started stream

        Raises:
            ValueError: If a stream with the same filename already exists
        """
        if config.filename in self.active_streams:
            raise ValueError(f"Stream already active for file: {config.filename}")

        # Configure deduplicator
        self.deduplicator = LineDeduplicator(
            window_size=config.window_size,
            similarity_threshold=config.similarity_threshold,
        )

        # Start appropriate task based on mode
        if config.mode == StreamMode.RENDER:
            task = asyncio.create_task(self._stream_render_task(config))
        elif config.mode == StreamMode.APPEND:
            task = asyncio.create_task(self._stream_append_task(config))
        else:
            raise ValueError(f"Unsupported stream mode: {config.mode}")

        self.active_streams[config.filename] = task
        logger.info(f"Started {config.mode} stream to {config.filename}")

        return config.filename

    async def stop_stream(self, filename: str) -> bool:
        """Stop a streaming task.

        Args:
            filename: Filename of the stream to stop

        Returns:
            True if stream was stopped, False if not found
        """
        task = self.active_streams.get(filename)
        if not task:
            return False

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        del self.active_streams[filename]
        logger.info(f"Stopped stream to {filename}")

        return True

    def get_stream_status(self) -> Dict[str, Any]:
        """Get status of all active streams.

        Returns:
            Dictionary with stream status information
        """
        status = {}
        for filename, task in self.active_streams.items():
            status[filename] = {
                "active": not task.done(),
                "cancelled": task.cancelled(),
                "exception": str(task.exception())
                if task.done() and task.exception()
                else None,
            }
        return status

    async def stop_all_streams(self) -> None:
        """Stop all active streaming tasks."""
        for filename in list(self.active_streams.keys()):
            await self.stop_stream(filename)

    async def _stream_render_task(self, config: StreamConfig) -> None:
        """Background task for render mode (overwrite file).

        Args:
            config: Streaming configuration
        """
        while True:
            try:
                # Get rendered output (same as TUI)
                output = self.session.get_rendered_output(lines=120)

                # Atomic write (temp file + rename)
                temp_file = f"{config.filename}.tmp"
                async with aiofiles.open(temp_file, "w") as f:
                    await f.write(output)

                # Atomic rename
                os.replace(temp_file, config.filename)

                logger.debug(f"Rendered stream written to {config.filename}")

                await asyncio.sleep(config.interval)

            except asyncio.CancelledError:
                logger.debug(f"Render stream task cancelled for {config.filename}")
                break
            except Exception as e:
                logger.error(f"Render stream error for {config.filename}: {e}")
                await asyncio.sleep(config.interval)  # Continue on error

    async def _stream_append_task(self, config: StreamConfig) -> None:
        """Background task for append mode (append with deduplication).

        Args:
            config: Streaming configuration
        """
        while True:
            try:
                # Get current buffer lines
                buffer_content = self.session.buffer.get_last(config.window_size)
                new_lines = buffer_content.splitlines()

                # Read existing file tail
                existing_lines = await self._read_file_tail(
                    config.filename, config.window_size
                )

                # Compute diff using deduplicator
                lines_to_append = self.deduplicator.compute_diff(
                    existing_lines, new_lines
                )

                # Append if there are new lines
                if lines_to_append:
                    async with aiofiles.open(config.filename, "a") as f:
                        await f.write("\n".join(lines_to_append) + "\n")

                    logger.debug(
                        f"Appended {len(lines_to_append)} lines to {config.filename}"
                    )

                await asyncio.sleep(config.interval)

            except asyncio.CancelledError:
                logger.debug(f"Append stream task cancelled for {config.filename}")
                break
            except Exception as e:
                logger.error(f"Append stream error for {config.filename}: {e}")
                await asyncio.sleep(config.interval)  # Continue on error

    async def _read_file_tail(self, filename: str, max_lines: int) -> list[str]:
        """Read the tail of a file.

        Args:
            filename: File to read
            max_lines: Maximum number of lines to read

        Returns:
            List of lines from the file tail
        """
        if not os.path.exists(filename):
            return []

        try:
            async with aiofiles.open(filename, "r") as f:
                content = await f.read()
                lines = content.splitlines()
                return lines[-max_lines:] if len(lines) > max_lines else lines
        except Exception as e:
            logger.error(f"Error reading file tail for {filename}: {e}")
            return []
