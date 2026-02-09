"""API endpoints for stream-to-file functionality."""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from silc.stream.config import StreamConfig
from silc.stream.streaming_service import StreamingService

router = APIRouter(prefix="/stream", tags=["streaming"])


def get_streaming_service(session: Any = Depends(lambda: None)) -> StreamingService:  # type: ignore
    """Get streaming service instance.

    This dependency will be overridden in the main API server
    to provide the actual session instance.

    Args:
        session: Session instance (injected)

    Returns:
        StreamingService instance
    """
    return StreamingService(session)


@router.post("/start")
async def start_streaming(
    config: StreamConfig,
    service: StreamingService = Depends(get_streaming_service),
) -> dict[str, str]:
    """Start a new streaming task.

    Args:
        config: Streaming configuration
        service: Streaming service instance

    Returns:
        Success message with filename

    Raises:
        HTTPException: If stream cannot be started
    """
    try:
        filename = await service.start_stream(config)
        return {"status": "started", "filename": filename, "mode": config.mode}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to start stream: {e}"
        ) from e


@router.post("/stop")
async def stop_streaming(
    filename: str,
    service: StreamingService = Depends(get_streaming_service),
) -> dict[str, str]:
    """Stop a streaming task.

    Args:
        filename: Filename of the stream to stop
        service: Streaming service instance

    Returns:
        Success message

    Raises:
        HTTPException: If stream cannot be stopped
    """
    try:
        stopped = await service.stop_stream(filename)
        if stopped:
            return {"status": "stopped", "filename": filename}
        raise HTTPException(
            status_code=404, detail=f"No active stream found for: {filename}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to stop stream: {e}"
        ) from e


@router.get("/status")
async def get_stream_status(
    service: StreamingService = Depends(get_streaming_service),
) -> dict[str, Any]:
    """Get status of all active streams.

    Args:
        service: Streaming service instance

    Returns:
        Dictionary with stream status information
    """
    try:
        status = service.get_stream_status()
        return {"status": "success", "streams": status}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get stream status: {e}"
        ) from e
