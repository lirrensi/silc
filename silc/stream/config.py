"""Configuration models for stream-to-file functionality."""

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class StreamMode(str, Enum):
    """Streaming mode enumeration."""

    RENDER = "render"  # Overwrite file with current TUI state
    APPEND = "append"  # Append only new/changed lines with deduplication


class StreamConfig(BaseModel):
    """Configuration for stream-to-file operations."""

    mode: StreamMode = Field(..., description="Streaming mode (render or append)")
    filename: str = Field(..., description="Output filename")
    interval: int = Field(
        default=5, ge=1, le=3600, description="Refresh interval in seconds"
    )
    window_size: int = Field(
        default=2000, ge=100, le=10000, description="Deduplication window size in lines"
    )
    similarity_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Similarity threshold for fuzzy matching (0.0-1.0)",
    )
    max_file_size_mb: int = Field(
        default=100, ge=1, le=1000, description="Maximum file size before rotation (MB)"
    )
    rotation_policy: Literal["none", "size", "time"] = Field(
        default="size", description="File rotation policy"
    )

    class Config:
        """Pydantic configuration."""

        use_enum_values = True
