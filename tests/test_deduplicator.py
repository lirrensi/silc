"""Unit tests for the line deduplicator."""

import pytest

from silc.stream.deduplicator import LineDeduplicator


class TestLineDeduplicator:
    """Test suite for LineDeduplicator."""

    def test_exact_match_detection(self) -> None:
        """Test that exact matches are detected and filtered out."""
        deduplicator = LineDeduplicator()
        existing = ["line1", "line2", "line3"]
        new = ["line1", "line4", "line2", "line5"]

        diff = deduplicator.compute_diff(existing, new)

        assert "line1" not in diff
        assert "line2" not in diff
        assert "line4" in diff
        assert "line5" in diff

    def test_fuzzy_match_detection(self) -> None:
        """Test that fuzzy matches are detected with configurable threshold."""
        deduplicator = LineDeduplicator(similarity_threshold=0.85)
        existing = ["Hello World", "Test Line"]
        new = ["Hello World!", "Test Line ", "New Line"]

        diff = deduplicator.compute_diff(existing, new)

        # "Hello World!" should be similar to "Hello World" (85%+)
        assert "Hello World!" not in diff
        # "Test Line " should be similar to "Test Line" (85%+)
        assert "Test Line " not in diff
        # "New Line" should be novel
        assert "New Line" in diff

    def test_ansi_code_stripping(self) -> None:
        """Test that ANSI escape codes are stripped during normalization."""
        deduplicator = LineDeduplicator()
        existing = ["Hello World"]
        new = ["\x1b[31mHello World\x1b[0m", "New Line"]

        diff = deduplicator.compute_diff(existing, new)

        # ANSI codes should be stripped, making "Hello World" match
        assert "\x1b[31mHello World\x1b[0m" not in diff
        assert "New Line" in diff

    def test_whitespace_normalization(self) -> None:
        """Test that whitespace is normalized during comparison."""
        deduplicator = LineDeduplicator()
        existing = ["Hello World"]
        new = ["Hello  World", "Hello\tWorld", "New Line"]

        diff = deduplicator.compute_diff(existing, new)

        # Whitespace should be collapsed, making both match
        assert "Hello  World" not in diff
        assert "Hello\tWorld" not in diff
        assert "New Line" in diff

    def test_case_insensitive_matching(self) -> None:
        """Test that matching is case-insensitive."""
        deduplicator = LineDeduplicator()
        existing = ["hello world"]
        new = ["HELLO WORLD", "Hello World", "new line"]

        diff = deduplicator.compute_diff(existing, new)

        # Case should be normalized, making all match
        assert "HELLO WORLD" not in diff
        assert "Hello World" not in diff
        assert "new line" in diff

    def test_empty_lines_handling(self) -> None:
        """Test that empty lines are handled correctly."""
        deduplicator = LineDeduplicator()
        existing = ["line1", "", "line2"]
        new = ["", "line3", ""]

        diff = deduplicator.compute_diff(existing, new)

        # Empty lines should be filtered out
        assert "" not in diff
        assert "line3" in diff

    def test_window_size_limit(self) -> None:
        """Test that deduplication window is limited to configured size."""
        deduplicator = LineDeduplicator(window_size=3)
        existing = ["line1", "line2", "line3", "line4", "line5"]
        new = ["line1", "line4", "line6"]

        diff = deduplicator.compute_diff(existing, new)

        # "line1" should NOT match (outside window - only last 3 lines are cached)
        assert "line1" in diff
        # "line4" should match (in window - last 3 lines are line3, line4, line5)
        assert "line4" not in diff
        # "line6" should be novel
        assert "line6" in diff

    def test_no_existing_lines(self) -> None:
        """Test behavior when there are no existing lines."""
        deduplicator = LineDeduplicator()
        existing = []
        new = ["line1", "line2", "line3"]

        diff = deduplicator.compute_diff(existing, new)

        # All lines should be novel
        assert len(diff) == 3
        assert "line1" in diff
        assert "line2" in diff
        assert "line3" in diff

    def test_no_new_lines(self) -> None:
        """Test behavior when there are no new lines."""
        deduplicator = LineDeduplicator()
        existing = ["line1", "line2"]
        new = []

        diff = deduplicator.compute_diff(existing, new)

        # No lines should be returned
        assert len(diff) == 0

    def test_all_duplicate_lines(self) -> None:
        """Test behavior when all new lines are duplicates."""
        deduplicator = LineDeduplicator()
        existing = ["line1", "line2", "line3"]
        new = ["line1", "line2", "line3"]

        diff = deduplicator.compute_diff(existing, new)

        # No lines should be returned
        assert len(diff) == 0

    def test_length_ratio_filtering(self) -> None:
        """Test that lines with very different lengths are not considered similar."""
        deduplicator = LineDeduplicator(similarity_threshold=0.85)
        existing = ["Hello"]
        new = ["Hello World This Is A Very Long Line"]

        diff = deduplicator.compute_diff(existing, new)

        # Length ratio should be too different, so it should be considered novel
        assert "Hello World This Is A Very Long Line" in diff

    def test_normalize_line(self) -> None:
        """Test the normalize_line method directly."""
        deduplicator = LineDeduplicator()

        # Test ANSI stripping
        assert deduplicator.normalize_line("\x1b[31mHello\x1b[0m") == "hello"

        # Test whitespace collapsing
        assert deduplicator.normalize_line("Hello  World") == "hello world"

        # Test case normalization
        assert deduplicator.normalize_line("HELLO WORLD") == "hello world"

        # Test tab handling
        assert deduplicator.normalize_line("Hello\tWorld") == "hello world"

        # Test empty string
        assert deduplicator.normalize_line("") == ""

    def test_is_similar(self) -> None:
        """Test the is_similar method directly."""
        deduplicator = LineDeduplicator(similarity_threshold=0.85)

        # Test exact match
        assert deduplicator.is_similar("Hello World", "Hello World")

        # Test similar strings
        assert deduplicator.is_similar("Hello World", "Hello World!")

        # Test different strings
        assert not deduplicator.is_similar("Hello", "Goodbye")

        # Test empty strings
        assert deduplicator.is_similar("", "")

    def test_reset_cache(self) -> None:
        """Test that the cache can be reset."""
        deduplicator = LineDeduplicator()
        existing = ["line1", "line2"]
        new = ["line1", "line3"]

        # First computation should populate cache
        diff1 = deduplicator.compute_diff(existing, new)
        assert "line1" not in diff1

        # Reset cache
        deduplicator.reset_cache()

        # Second computation should work the same
        diff2 = deduplicator.compute_diff(existing, new)
        assert "line1" not in diff2

    def test_performance_with_large_datasets(self) -> None:
        """Test performance with large line counts."""
        deduplicator = LineDeduplicator(window_size=1000)
        existing = [f"existing_line_{i}" for i in range(1000)]
        new = [f"new_line_{i}" for i in range(500, 1500)]

        # Should complete in reasonable time
        diff = deduplicator.compute_diff(existing, new)

        # All new lines should be novel (different prefix)
        assert len(diff) == 1000
        assert "new_line_500" in diff
        assert "new_line_1499" in diff
