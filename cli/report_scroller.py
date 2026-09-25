"""Vertical scrolling for the CLI "Current Report" panel.

Rich crops a renderable that is taller than its layout section, so a long
report loses everything below the fold and there is no way to reach it. This
module renders the report to lines once, keeps a scroll offset, and shows the
slice that fits the section.

Keys: Up/Down move one line, Page Up/Page Down move one window, Home/End jump
to the first and last line. The key reader runs in a background thread and
never echoes what it reads, so the live display stays clean.
"""

from __future__ import annotations

import os
import re
import sys
import threading
import time
from typing import Callable, List, Optional

from rich.console import Group, RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text

# Key names used by the scroller, independent of the platform.
KEY_UP = "up"
KEY_DOWN = "down"
KEY_PAGE_UP = "pageup"
KEY_PAGE_DOWN = "pagedown"
KEY_HOME = "home"
KEY_END = "end"

SCROLL_KEYS = (KEY_UP, KEY_DOWN, KEY_PAGE_UP, KEY_PAGE_DOWN, KEY_HOME, KEY_END)

# Scan codes the Windows console sends after a 0x00 or 0xE0 prefix.
_WINDOWS_SCAN_CODES = {
    "H": KEY_UP,
    "P": KEY_DOWN,
    "I": KEY_PAGE_UP,
    "Q": KEY_PAGE_DOWN,
    "G": KEY_HOME,
    "O": KEY_END,
}

# Escape sequences for the same keys, both cursor and keypad forms.
_ANSI_KEYS = {
    "A": KEY_UP,
    "B": KEY_DOWN,
    "H": KEY_HOME,
    "F": KEY_END,
    "1~": KEY_HOME,
    "4~": KEY_END,
    "5~": KEY_PAGE_UP,
    "6~": KEY_PAGE_DOWN,
    "7~": KEY_HOME,
    "8~": KEY_END,
}

# ESC [ 1 ; 5 A, ESC O A, ESC [ 5 ~, where the letter group is the
# application cursor mode introducer and the digit group is absent there.
_ANSI_SEQUENCE = re.compile("\x1b(?:O([@-~])|\\[([0-9;]*)([@-~]))")

# Panel chrome: one border column and one padding column per side, and one
# border row plus one padding row per side.
PANEL_CHROME_WIDTH = 6
PANEL_CHROME_HEIGHT = 4

# Used when the section reports no height, which happens outside a layout.
FALLBACK_WINDOW = 20


def decode_windows_key(first: str, second: str = "") -> Optional[str]:
    """Return the key name for a Windows console read, or None to ignore it.

    A key press is two characters for the navigation keys: a 0x00 or 0xE0
    prefix followed by a scan code. Anything else is a plain character and is
    ignored, so typing a letter never quits or changes the display.
    """
    if first in ("\x00", "\xe0"):
        return _WINDOWS_SCAN_CODES.get(second.upper())
    return None


def parse_ansi_keys(data: str) -> List[str]:
    """Return the key names in a chunk of terminal input."""
    keys = []

    for match in _ANSI_SEQUENCE.finditer(data):
        application_letter, digits, final = match.groups()

        if application_letter is not None:
            key = _ANSI_KEYS.get(application_letter)
        elif final == "~":
            key = _ANSI_KEYS.get(f"{digits}~")
        else:
            key = _ANSI_KEYS.get(final)

        if key:
            keys.append(key)

    return keys


class ReportScroller:
    """Scroll offset over the rendered report lines."""

    def __init__(self) -> None:
        self.offset = 0
        self._pending: List[str] = []

    def queue_key(self, key: str) -> None:
        """Record a key press. Called from the key reader thread."""
        if key in SCROLL_KEYS:
            self._pending.append(key)

    def apply_pending(self, total_lines: int, window: int) -> None:
        """Apply queued key presses and clamp the offset to the content.

        Rendering calls this, so a press that arrives between two frames still
        lands, and several presses stack up in order.
        """
        limit = self.max_offset(total_lines, window)

        for key in self._pending:
            self.handle_key(key, total_lines, window)

        self._pending.clear()
        self.offset = max(0, min(self.offset, limit))

    def handle_key(self, key: str, total_lines: int, window: int) -> None:
        """Move the offset for one key press."""
        limit = self.max_offset(total_lines, window)
        # Keep the last line of the previous window visible on a page move.
        step = max(1, window - 1)

        if key == KEY_UP:
            self.offset -= 1
        elif key == KEY_DOWN:
            self.offset += 1
        elif key == KEY_PAGE_UP:
            self.offset -= step
        elif key == KEY_PAGE_DOWN:
            self.offset += step
        elif key == KEY_HOME:
            self.offset = 0
        elif key == KEY_END:
            self.offset = limit
        else:
            return

        self.offset = max(0, min(self.offset, limit))

    def max_offset(self, total_lines: int, window: int) -> int:
        """Return the largest offset that keeps the last line in view."""
        return max(0, total_lines - max(1, window))

    def reset(self) -> None:
        """Return to the top and drop queued keys."""
        self.offset = 0
        self._pending.clear()


class ScrollableReport:
    """Renderable that shows one window of the current report.

    The panel is rebuilt on every render, so a key press is reflected on the
    next live refresh without touching the layout.
    """

    def __init__(
        self,
        get_report: Callable[[], str],
        scroller: ReportScroller,
        title: str = "Current Report",
        border_style: str = "green",
    ) -> None:
        self._get_report = get_report
        self._scroller = scroller
        self._title = title
        self._border_style = border_style

    def __rich_console__(self, console, options):
        report = self._get_report() or ""

        window = self._window(options)
        lines = self._render_lines(console, report, options)
        self._scroller.apply_pending(len(lines), window)

        limit = self._scroller.max_offset(len(lines), window)
        offset = max(0, min(self._scroller.offset, limit))
        visible = lines[offset : offset + window]

        body: RenderableType = (
            Group(*(_line_text(line) for line in visible)) if visible else Text("")
        )

        yield Panel(
            body,
            title=self._panel_title(offset, len(lines), window),
            border_style=self._border_style,
            padding=(1, 2),
        )

    def _window(self, options) -> int:
        """Return how many report lines fit in the panel."""
        height = options.height or FALLBACK_WINDOW
        return max(1, height - PANEL_CHROME_HEIGHT)

    def _render_lines(self, console, report: str, options) -> List[list]:
        """Render the markdown report to styled lines at the panel width."""
        if not report.strip():
            return []

        width = max(8, options.max_width - PANEL_CHROME_WIDTH)
        render_options = options.update(width=width, height=None)
        return console.render_lines(Markdown(report), render_options, pad=False)

    def _panel_title(self, offset: int, total: int, window: int) -> str:
        """Return the panel title with the visible range and key hints."""
        if total <= window:
            return self._title

        first = offset + 1
        last = min(total, offset + window)
        title = f"{self._title} [{first}-{last}/{total}]"

        if offset > 0 and last < total:
            return f"{title} Up/Down scroll"
        if offset > 0:
            return f"{title} Up scroll (at end)"
        return f"{title} Down scroll"


def _line_text(line: list) -> Text:
    """Turn one rendered line back into a Text that keeps its styles."""
    return Text.assemble(*[(segment.text, segment.style) for segment in line])


class KeyReader:
    """Read navigation keys in the background, without echoing them."""

    def __init__(
        self, on_key: Callable[[str], None], poll_interval: float = 0.03
    ) -> None:
        self._on_key = on_key
        self._poll_interval = poll_interval
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None

    @staticmethod
    def is_supported() -> bool:
        """True when key input is possible, which excludes piped stdin."""
        try:
            return bool(sys.stdin) and sys.stdin.isatty()
        except (AttributeError, ValueError):
            return False

    def start(self) -> bool:
        """Start reading keys. Returns False when the terminal cannot be read."""
        if not self.is_supported():
            return False

        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run, name="report-scroller-keys", daemon=True
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop reading keys and wait for the terminal to be restored."""
        self._stop.set()

        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def __enter__(self) -> "KeyReader":
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()

    def _run(self) -> None:
        if os.name == "nt":
            self._run_windows()
        else:
            self._run_posix()

    def _run_windows(self) -> None:
        import msvcrt

        while not self._stop.is_set():
            if msvcrt.kbhit():
                first = msvcrt.getch()
                second = msvcrt.getch() if first in ("\x00", "\xe0") else ""
                key = decode_windows_key(first, second)
                if key:
                    self._on_key(key)
            time.sleep(self._poll_interval)

    def _run_posix(self) -> None:
        import select
        import termios
        import tty

        file_descriptor = sys.stdin.fileno()
        saved = termios.tcgetattr(file_descriptor)

        try:
            # cbreak, not raw: input is unbuffered and not echoed, while the
            # output side keeps processing the control codes Rich writes.
            tty.setcbreak(file_descriptor)

            while not self._stop.is_set():
                readable, _, _ = select.select([sys.stdin], [], [], self._poll_interval)
                if not readable:
                    continue

                data = os.read(file_descriptor, 16).decode("utf-8", errors="ignore")
                for key in parse_ansi_keys(data):
                    self._on_key(key)
        finally:
            termios.tcsetattr(file_descriptor, termios.TCSADRAIN, saved)
