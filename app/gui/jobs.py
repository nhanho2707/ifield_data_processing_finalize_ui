"""Background jobs: run core functions in a worker thread and forward their reports to the UI."""
import time
import traceback

from PySide6.QtCore import QObject, QThread, Qt, Signal

from app.core.errors import Cancelled, IFieldError
from app.core.reporter import Reporter

QUEUED = Qt.ConnectionType.QueuedConnection


class ReporterSignals(QObject):
    log = Signal(str, str)                    # level, message
    progress = Signal(str, int, int)          # description, current, total (-1 = unknown)
    step = Signal(str, str, str, float, str)  # key, title, status, elapsed, error


class QtReporter(Reporter):
    """Reporter whose callbacks become Qt signals (safe to emit from the worker thread)."""

    def __init__(self):
        super().__init__()
        self.signals = ReporterSignals()
        self._last_progress = 0.0

    def emit(self, level, message):
        self.signals.log.emit(level, message)

    def on_progress(self, desc, current, total):
        # Row loops can be long: limit the UI updates to ~20 per second.
        now = time.monotonic()
        if current in (0, total) or now - self._last_progress >= 0.05:
            self._last_progress = now
            self.signals.progress.emit(desc, current, -1 if total is None else total)

    def on_step(self, key, title, status, elapsed=None, error=None):
        self.signals.step.emit(key, title, status, elapsed or 0.0, error or "")


class _Worker(QThread):
    succeeded = Signal(object)
    failed = Signal(str, bool)  # message, cancelled

    def __init__(self, fn, reporter):
        super().__init__()
        self._fn = fn
        self._reporter = reporter

    def run(self):
        try:
            self.succeeded.emit(self._fn(self._reporter))
        except Cancelled as ex:
            self.failed.emit(str(ex), True)
        except IFieldError as ex:
            self.failed.emit(str(ex), False)
        except Exception:
            self.failed.emit(traceback.format_exc(), False)


class JobManager(QObject):
    """Starts jobs; at most one exclusive job (anything touching project data) at a time."""

    busy_changed = Signal(bool)
    job_started = Signal(object, str)         # QtReporter, title
    job_finished = Signal(str, bool, bool, str)  # title, ok, cancelled, error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self._workers = {}
        self._exclusive = None

    @property
    def busy(self) -> bool:
        return self._exclusive is not None

    @property
    def active(self) -> bool:
        """Any job still running, exclusive or not."""
        return bool(self._workers)

    @property
    def current_reporter(self) -> QtReporter | None:
        return self._workers[self._exclusive][0] if self._exclusive is not None else None

    def start(self, title: str, fn, on_success=None, on_failure=None, exclusive: bool = True) -> QtReporter | None:
        """Run fn(reporter) in a worker thread. Callbacks run in the UI thread."""
        if exclusive and self.busy:
            return None

        reporter = QtReporter()
        worker = _Worker(fn, reporter)
        self._workers[worker] = (reporter, title, on_success, on_failure, exclusive)

        worker.succeeded.connect(lambda result, w=worker: self._done(w, True, result, "", False), QUEUED)
        worker.failed.connect(lambda message, cancelled, w=worker: self._done(w, False, None, message, cancelled), QUEUED)
        worker.finished.connect(lambda w=worker: self._cleanup(w), QUEUED)

        if exclusive:
            self._exclusive = worker
            self.busy_changed.emit(True)
            self.job_started.emit(reporter, title)
        worker.start()
        return reporter

    def cancel(self):
        if self.current_reporter is not None:
            self.current_reporter.cancel()

    def _done(self, worker, ok, result, message, cancelled):
        reporter, title, on_success, on_failure, exclusive = self._workers[worker]
        if exclusive:
            self._exclusive = None
            self.busy_changed.emit(False)
            self.job_finished.emit(title, ok, cancelled, message)

        if ok and on_success:
            on_success(result)
        elif not ok and on_failure:
            on_failure(message, cancelled)

    def _cleanup(self, worker):
        self._workers.pop(worker, None)
        worker.deleteLater()
