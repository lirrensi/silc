"""Line deduplication engine for stream-to-file append mode."""

import difflib
import re
from typing import List, Set


class LineDeduplicator:
    """Two-stage line deduplicator with exact and fuzzy matching."""

    def __init__(self, window_size: int = 2000, similarity_threshold: float = 0.85):
        """Initialize deduplicator.

        Args:
            window_size: Maximum number of lines to keep in comparison window
            similarity_threshold: Minimum similarity ratio (0.0-1.0) for fuzzy matches
        """
        self.window_size = window_size
        self.similarity_threshold = similarity_threshold
        self._exact_cache: Set[str] = set()  # For O(1) exact match checks
        self._cache_max_size: int = window_size * 2  # Bound cache growth
        self._ansi_pattern = re.compile(r"\x1b\[[0-9;]*m")  # ANSI escape codes

    def compute_diff(
        self, existing_lines: List[str], new_lines: List[str]
    ) -> List[str]:
        """Compute diff between existing and new lines with deduplication.

        Args:
            existing_lines: Lines already in the file
            new_lines: New lines to potentially append

        Returns:
            List of lines that should be appended (without duplicates)
        """
        if not new_lines:
            return []

        # Update exact cache with existing lines (limit to window size)
        self._update_cache(existing_lines)

        # Stage 1: Fast exact match filtering
        novel_lines = []
        for line in new_lines:
            normalized = self.normalize_line(line)
            if normalized and normalized not in self._exact_cache:
                novel_lines.append(line)

        # Stage 2: Fuzzy matching for remaining lines
        if not existing_lines or not novel_lines:
            return novel_lines

        deduplicated_lines = []
        for line in novel_lines:
            if not self._is_fuzzy_match(line, existing_lines):
                deduplicated_lines.append(line)

        return deduplicated_lines

    def normalize_line(self, line: str) -> str:
        """Normalize line for comparison.

        - Strips ANSI escape codes
        - Collapses whitespace
        - Converts to lowercase
        - Strips leading/trailing whitespace

        Args:
            line: Raw line string

        Returns:
            Normalized line string
        """
        if not line:
            return ""

        # Remove ANSI escape codes
        line = self._ansi_pattern.sub("", line)

        # Collapse whitespace and convert to lowercase
        line = " ".join(line.split()).lower()

        return line.strip()

    def is_similar(self, line1: str, line2: str) -> bool:
        """Check if two lines are similar above threshold.

        Args:
            line1: First line to compare
            line2: Second line to compare

        Returns:
            True if lines are similar enough, False otherwise
        """
        norm1 = self.normalize_line(line1)
        norm2 = self.normalize_line(line2)

        if not norm1 or not norm2:
            return norm1 == norm2

        # Quick length check (if lengths differ too much, they're not similar)
        len_ratio = min(len(norm1), len(norm2)) / max(len(norm1), len(norm2))
        if len_ratio < 0.5:  # Lengths differ by more than 2x
            return False

        # Use SequenceMatcher for fuzzy comparison
        matcher = difflib.SequenceMatcher(None, norm1, norm2)
        return matcher.ratio() >= self.similarity_threshold

    def _update_cache(self, existing_lines: List[str]) -> None:
        """Update exact match cache with existing lines.

        Args:
            existing_lines: Lines to add to cache
        """
        # Bound cache: if over limit, clear and rebuild from recent lines only
        if len(self._exact_cache) > self._cache_max_size:
            self._exact_cache.clear()

        # Limit cache to window size
        lines_to_cache = existing_lines[-self.window_size :]

        # Update cache with normalized lines
        for line in lines_to_cache:
            normalized = self.normalize_line(line)
            if normalized:
                self._exact_cache.add(normalized)

    def _is_fuzzy_match(self, line: str, existing_lines: List[str]) -> bool:
        """Check if line fuzzy matches any existing line.

        Args:
            line: Line to check
            existing_lines: Existing lines to compare against

        Returns:
            True if fuzzy match found, False otherwise
        """
        # Only check against recent lines (limit comparison window)
        recent_lines = existing_lines[-self.window_size :]

        for existing in recent_lines:
            if self.is_similar(line, existing):
                return True

        return False

    def reset_cache(self) -> None:
        """Reset the exact match cache."""
        self._exact_cache.clear()
