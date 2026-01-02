from silc.core.cleaner import clean_output, collapse_progress_bars


def test_clean_output_strips_control_sequences_and_blanks() -> None:
    lines = [
        "\x1b[31mHello\x1b[0m\r\n",
        "progress: 10%",
        "progress: 99%",
        "partial\rfinal",
        "",
        " \t ",
        "done",
    ]

    cleaned = clean_output(lines)
    assert "progress: 99%" in cleaned
    assert "final" in cleaned
    assert "done" in cleaned
    assert "progress: 10%" not in cleaned
    cleaned_lines = cleaned.splitlines()
    assert cleaned_lines.count("") <= 2


def test_collapse_progress_bars_keeps_latest_frame() -> None:
    lines = ["progress: 10%", "progress: 20%", "done", "progress: 30%"]
    collapsed = collapse_progress_bars(lines)
    assert collapsed == ["progress: 20%", "done", "progress: 30%"]
