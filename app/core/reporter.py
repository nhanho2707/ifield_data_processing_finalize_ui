import sys
import threading
from contextlib import contextmanager, redirect_stdout
from datetime import datetime
from pathlib import Path

from tqdm import tqdm

from app.core.errors import Cancelled


class Reporter:
    """Channel between the core and its front-end (CLI or GUI).

    The core only talks to this object: it logs messages, reports progress of
    long loops, announces step status changes and checks for cancellation.
    A GUI subclasses it and overrides `emit`, `on_progress` and `on_step`.
    """

    def __init__(self):
        self.cancel_event = threading.Event()
        self._log_file = None

    # --- Hooks for front-ends -------------------------------------------------

    def emit(self, level: str, message: str):
        """Display one log message. level: info | warning | error | output."""

    def on_progress(self, desc: str, current: int, total: int | None):
        """Progress of the current loop (total is None when unknown)."""

    def on_step(self, key: str, title: str, status: str, elapsed: float | None = None, error: str | None = None):
        """status: running | done | skipped | failed | cancelled."""

    # --- Used by the core -----------------------------------------------------

    def _write_log_file(self, level: str, message: str):
        if self._log_file is not None:
            self._log_file.write(f"{datetime.now():%H:%M:%S} [{level.upper()}] {message}\n")
            self._log_file.flush()

    def log(self, message, level: str = "info"):
        message = str(message)
        self._write_log_file(level, message)
        self.emit(level, message)

    def step(self, key: str, title: str, status: str, elapsed: float | None = None, error: str | None = None):
        """Record a step status change in the log file, then notify the front-end."""
        line = f"--- {title}: {status}" + (f" ({elapsed:.1f}s)" if elapsed is not None else "")
        self._write_log_file("error" if status == "failed" else "info", line)
        if error:
            self._write_log_file("error", error)
        self.on_step(key, title, status, elapsed, error)

    def info(self, message):
        self.log(message, "info")

    def warning(self, message):
        self.log(message, "warning")

    def error(self, message):
        self.log(message, "error")

    def cancel(self):
        self.cancel_event.set()

    def check_cancelled(self):
        if self.cancel_event.is_set():
            raise Cancelled("Cancelled by user.")

    def progress(self, iterable, desc: str, total: int | None = None):
        """Iterate while reporting progress and honouring cancellation."""
        if total is None and hasattr(iterable, "__len__"):
            total = len(iterable)
        self.on_progress(desc, 0, total)
        for i, item in enumerate(iterable, 1):
            self.check_cancelled()
            yield item
            self.on_progress(desc, i, total)

    @contextmanager
    def log_to_file(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            self._log_file = f
            try:
                yield path
            finally:
                self._log_file = None

    @contextmanager
    def capture_stdout(self):
        """Route print() output of the legacy `object` package into the log."""
        with redirect_stdout(_LineWriter(lambda line: self.log(line, "output"))):
            yield


class _LineWriter:
    def __init__(self, callback):
        self._callback = callback
        self._buffer = ""

    def write(self, text):
        self._buffer += text
        *lines, self._buffer = self._buffer.split("\n")
        for line in lines:
            if line.strip():
                self._callback(line.rstrip())
        return len(text)

    def flush(self):
        if self._buffer.strip():
            self._callback(self._buffer.rstrip())
        self._buffer = ""


class ConsoleReporter(Reporter):
    """Reporter for the command line: tqdm progress bars and plain messages."""

    def __init__(self, stream=None):
        super().__init__()
        # Keep the real stdout: capture_stdout() swaps sys.stdout while a job runs.
        self._stream = stream or sys.stdout

    def emit(self, level, message):
        prefix = "" if level in ("info", "output") else f"[{level.upper()}] "
        tqdm.write(prefix + message, file=self._stream)

    def on_step(self, key, title, status, elapsed=None, error=None):
        match status:
            case "running":
                tqdm.write(f"\n=== {title} ===", file=self._stream)
            case "skipped":
                tqdm.write(f"--- {title}: skipped", file=self._stream)
            case "done":
                tqdm.write(f"--- {title}: done ({elapsed:.1f}s)", file=self._stream)
            case _:
                tqdm.write(f"--- {title}: {status.upper()}", file=self._stream)

    def progress(self, iterable, desc, total=None):
        if total is None and hasattr(iterable, "__len__"):
            total = len(iterable)
        with tqdm(total=total, desc=desc, file=sys.stderr) as bar:
            for item in iterable:
                self.check_cancelled()
                yield item
                bar.update()
