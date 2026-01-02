from silc.core.raw_buffer import RawByteBuffer


def test_append_updates_cursor_and_trims_overflow() -> None:
    buffer = RawByteBuffer(maxlen=5)
    buffer.append(b"abcdefg")

    assert buffer.get_bytes() == b"cdefg"
    assert buffer.cursor == 7

    chunk, cursor = buffer.get_since(0)
    assert chunk == b"cdefg"
    assert cursor == buffer.cursor

    empty_chunk, cursor_after_end = buffer.get_since(buffer.cursor + 10)
    assert empty_chunk == b""
    assert cursor_after_end == buffer.cursor


def test_get_last_respects_line_limit_and_clears() -> None:
    buffer = RawByteBuffer()
    buffer.append(b"one\ntwo\nthree\n")

    assert buffer.get_last(2) == ["two", "three"]
    assert buffer.get_last(None) == ["one", "two", "three"]

    buffer.clear()
    assert buffer.get_last() == []
    assert buffer.cursor == 0


def test_get_since_handles_trimmed_cursor() -> None:
    buffer = RawByteBuffer(maxlen=4)
    buffer.append(b"1234")
    first_cursor = buffer.cursor
    buffer.append(b"56")

    trimmed_chunk, trimmed_cursor = buffer.get_since(0)
    assert trimmed_chunk == buffer.get_bytes()
    assert trimmed_cursor == buffer.cursor

    chunk_since_first, _ = buffer.get_since(first_cursor)
    assert chunk_since_first == b"56"
