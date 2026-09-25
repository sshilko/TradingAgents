"""Tests for the CLI 'Current Report' scroll window."""

import io
import os
import threading
import time

import pytest
from rich.console import Console

from cli.report_scroller import (
    KEY_DOWN,
    KEY_END,
    KEY_HOME,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_UP,
    KeyReader,
    ReportScroller,
    ScrollableReport,
    decode_windows_key,
    parse_ansi_keys,
)


def make_report(paragraphs: int = 60) -> str:
    """Return a markdown report tall enough to overflow the panel."""
    body = "\n\n".join(
        f"Paragraph {index} with some text." for index in range(1, paragraphs + 1)
    )
    return f"### Market Analysis\n{body}"


def render(reportable, console=None, width=100, height=40) -> str:
    """Render a renderable to text with a known size."""
    buffer = io.StringIO()
    console = console or Console(
        file=buffer,
        width=width,
        height=height,
        force_terminal=False,
        legacy_windows=False,
    )
    console.print(reportable)
    return buffer.getvalue()


def body_lines(text: str) -> list[str]:
    """Return the content lines of a rendered panel, borders stripped.

    The panel border rows are the only rows with corner characters, so they are
    dropped; every other row is report content.
    """
    lines = []
    for line in text.splitlines():
        if any(corner in line for corner in "\u256d\u256e\u2570\u256f"):
            continue
        stripped = line.strip().strip("\u2502").strip()
        if stripped:
            lines.append(stripped)
    return lines


@pytest.mark.unit
class TestKeyDecoding:
    def test_windows_extended_keys_map_to_names(self):
        # 0xE0 is the prefix the Windows console sends for a navigation key.
        assert decode_windows_key("\xe0", "H") == KEY_UP
        assert decode_windows_key("\xe0", "P") == KEY_DOWN
        assert decode_windows_key("\x00", "I") == KEY_PAGE_UP
        assert decode_windows_key("\x00", "Q") == KEY_PAGE_DOWN
        assert decode_windows_key("\xe0", "G") == KEY_HOME
        assert decode_windows_key("\xe0", "O") == KEY_END

    def test_windows_plain_characters_are_ignored(self):
        # A letter must never scroll or quit the run.
        assert decode_windows_key("q") is None
        assert decode_windows_key("\r") is None
        assert decode_windows_key("\xe0", "Z") is None

    def test_ansi_cursor_and_keypad_sequences(self):
        assert parse_ansi_keys("\x1b[A") == [KEY_UP]
        assert parse_ansi_keys("\x1b[B") == [KEY_DOWN]
        assert parse_ansi_keys("\x1bOA") == [KEY_UP]
        assert parse_ansi_keys("\x1bOB") == [KEY_DOWN]

    def test_ansi_page_home_end_sequences(self):
        assert parse_ansi_keys("\x1b[5~") == [KEY_PAGE_UP]
        assert parse_ansi_keys("\x1b[6~") == [KEY_PAGE_DOWN]
        assert parse_ansi_keys("\x1b[H") == [KEY_HOME]
        assert parse_ansi_keys("\x1b[F") == [KEY_END]
        assert parse_ansi_keys("\x1b[7~") == [KEY_HOME]
        assert parse_ansi_keys("\x1b[8~") == [KEY_END]

    def test_ansi_batch_and_ignored_text(self):
        # Ctrl+Down arrives with modifiers, and a typed character is skipped.
        assert parse_ansi_keys("q\x1b[1;5B\x1b[5~") == [KEY_DOWN, KEY_PAGE_UP]
        assert parse_ansi_keys("hello") == []
        assert parse_ansi_keys("") == []


@pytest.mark.unit
class TestScrollerOffset:
    def test_line_keys_move_one_line(self):
        scroller = ReportScroller()

        scroller.handle_key(KEY_DOWN, total_lines=100, window=20)
        assert scroller.offset == 1

        scroller.handle_key(KEY_UP, total_lines=100, window=20)
        assert scroller.offset == 0

    def test_page_keys_move_one_window(self):
        scroller = ReportScroller()

        scroller.handle_key(KEY_PAGE_DOWN, total_lines=100, window=20)
        assert scroller.offset == 19

        scroller.handle_key(KEY_PAGE_UP, total_lines=100, window=20)
        assert scroller.offset == 0

    def test_home_and_end_jump_to_the_bounds(self):
        scroller = ReportScroller()

        scroller.handle_key(KEY_END, total_lines=100, window=20)
        assert scroller.offset == 80

        scroller.handle_key(KEY_HOME, total_lines=100, window=20)
        assert scroller.offset == 0

    def test_offset_is_clamped_at_both_ends(self):
        scroller = ReportScroller()

        for _ in range(5):
            scroller.handle_key(KEY_UP, total_lines=100, window=20)
        assert scroller.offset == 0

        for _ in range(200):
            scroller.handle_key(KEY_DOWN, total_lines=100, window=20)
        assert scroller.offset == 80

    def test_content_shorter_than_the_window_has_no_scroll_range(self):
        scroller = ReportScroller()

        scroller.handle_key(KEY_END, total_lines=5, window=20)
        assert scroller.offset == 0

    def test_unknown_key_is_ignored(self):
        scroller = ReportScroller()
        scroller.offset = 5

        scroller.handle_key("q", total_lines=100, window=20)
        assert scroller.offset == 5

    def test_queued_keys_apply_in_order(self):
        scroller = ReportScroller()

        scroller.queue_key(KEY_DOWN)
        scroller.queue_key(KEY_DOWN)
        scroller.queue_key("q")  # not a scroll key, dropped on queue
        scroller.apply_pending(total_lines=100, window=20)

        assert scroller.offset == 2
        # The queue is drained, so a re-render does not move again.
        scroller.apply_pending(total_lines=100, window=20)
        assert scroller.offset == 2

    def test_offset_shrinks_when_the_report_gets_shorter(self):
        scroller = ReportScroller()
        scroller.offset = 50

        scroller.apply_pending(total_lines=30, window=20)
        assert scroller.offset == 10

    def test_reset_returns_to_the_top(self):
        scroller = ReportScroller()
        scroller.offset = 12
        scroller.queue_key(KEY_DOWN)

        scroller.reset()
        assert scroller.offset == 0

        scroller.apply_pending(total_lines=100, window=20)
        assert scroller.offset == 0


@pytest.mark.unit
class TestScrollableReportRender:
    def test_window_shows_the_top_of_the_report_first(self):
        text = render(ScrollableReport(lambda: make_report(), ReportScroller()))
        lines = body_lines(text)

        # Rich renders the heading without its markdown markers.
        assert lines[0].startswith("Market Analysis")
        assert lines[1].startswith("Paragraph 1")
        assert "Paragraph 60" not in text

    def test_scrolling_moves_the_visible_window(self):
        scroller = ReportScroller()
        reportable = ScrollableReport(lambda: make_report(), scroller)

        top = body_lines(render(reportable))

        scroller.queue_key(KEY_PAGE_DOWN)
        after_page = body_lines(render(reportable))

        scroller.queue_key(KEY_END)
        at_end = body_lines(render(reportable))

        assert after_page[0] != top[0]
        assert at_end[-1].startswith("Paragraph 60")

    def test_panel_title_reports_the_visible_range(self):
        text = render(ScrollableReport(lambda: make_report(), ReportScroller()))

        assert "Current Report [1-" in text
        assert "Down scroll" in text

    def test_panel_title_has_no_hint_when_the_report_fits(self):
        text = render(ScrollableReport(lambda: "Short report.", ReportScroller()))

        assert "Current Report" in text
        assert "scroll" not in text.lower()

    def test_waiting_panel_is_shown_for_an_empty_report(self):
        text = render(ScrollableReport(lambda: None, ReportScroller()))

        assert "Short report" not in text
        assert "Current Report" in text


@pytest.mark.unit
class TestKeyReader:
    def test_reader_does_not_start_without_a_terminal(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO())

        reader = KeyReader(lambda key: None)
        assert reader.is_supported() is False
        assert reader.start() is False

    def test_context_manager_is_safe_without_a_terminal(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO())
        pressed = []

        with KeyReader(pressed.append) as reader:
            assert reader.is_supported() is False

        assert pressed == []

    def test_stop_is_idempotent(self, monkeypatch):
        monkeypatch.setattr("sys.stdin", io.StringIO())
        reader = KeyReader(lambda key: None)

        reader.start()
        reader.stop()
        reader.stop()


class FakeTTY(io.StringIO):
    """Stdin stand-in that claims to be a terminal."""

    def isatty(self) -> bool:
        return True


@pytest.mark.skipif(os.name != "nt", reason="Windows console key input")
@pytest.mark.unit
class TestWindowsKeyLoop:
    def test_reader_reports_navigation_keys_only(self, monkeypatch):
        msvcrt = pytest.importorskip("msvcrt")

        # A Down press, an Up press, and a typed character that is ignored.
        pending = ["\xe0", "P", "\xe0", "H", "q"]
        lock = threading.Lock()

        def take() -> str:
            with lock:
                return pending.pop(0) if pending else ""

        monkeypatch.setattr("sys.stdin", FakeTTY())
        monkeypatch.setattr(msvcrt, "kbhit", lambda: bool(pending))
        monkeypatch.setattr(msvcrt, "getch", take)

        pressed: list[str] = []
        with KeyReader(pressed.append, poll_interval=0.01):
            deadline = time.monotonic() + 5.0
            while len(pressed) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)

        assert pressed == [KEY_DOWN, KEY_UP]

    def test_reader_stops_without_losing_pending_input(self, monkeypatch):
        msvcrt = pytest.importorskip("msvcrt")

        pending = ["\xe0", "O"]
        lock = threading.Lock()

        def take() -> str:
            with lock:
                return pending.pop(0) if pending else ""

        monkeypatch.setattr("sys.stdin", FakeTTY())
        monkeypatch.setattr(msvcrt, "kbhit", lambda: bool(pending))
        monkeypatch.setattr(msvcrt, "getch", take)

        pressed: list[str] = []
        reader = KeyReader(pressed.append, poll_interval=0.01)
        reader.start()
        try:
            deadline = time.monotonic() + 5.0
            while not pressed and time.monotonic() < deadline:
                time.sleep(0.01)
        finally:
            reader.stop()

        assert pressed == [KEY_END]
        assert reader.start() is True
        reader.stop()
