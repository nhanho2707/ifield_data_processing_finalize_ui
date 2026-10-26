import html
import os
from datetime import datetime

from PySide6.QtGui import QFontDatabase
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QPlainTextEdit, QProgressBar, QPushButton, QVBoxLayout,
                               QWidget)

from app.gui.i18n import tr
from app.gui.jobs import QUEUED, JobManager

LEVEL_COLORS = {
    "error": "#d13438",
    "warning": "#c97a00",
    "output": "#7a7a7a",
}


class LogPanel(QWidget):
    """Shared log + progress bar for every job, with a Stop button."""

    def __init__(self, jobs: JobManager, parent=None):
        super().__init__(parent)
        self.jobs = jobs

        self.title = QLabel(tr("Nhật ký"))
        self.title.setStyleSheet("font-weight: 600;")
        self.progress_label = QLabel("")
        self.progress_label.setMinimumWidth(200)
        self.progress = QProgressBar()
        self.progress.setMaximumWidth(260)
        self.progress.setTextVisible(True)
        self.progress.hide()

        self.stop_button = QPushButton(tr("Dừng"))
        self.stop_button.setToolTip(tr("Dừng sau dòng dữ liệu hiện tại. Một bước DMS đang chạy sẽ chạy xong rồi mới dừng."))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)

        clear_button = QPushButton(tr("Xoá"))
        clear_button.clicked.connect(lambda: self.view.clear())

        self.view = QPlainTextEdit()
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(20000)
        self.view.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)

        header = QHBoxLayout()
        header.addWidget(self.title)
        header.addStretch()
        header.addWidget(self.progress_label)
        header.addWidget(self.progress)
        header.addWidget(self.stop_button)
        header.addWidget(clear_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.addLayout(header)
        layout.addWidget(self.view)

        jobs.job_started.connect(self._job_started)
        jobs.job_finished.connect(self._job_finished)

    def append(self, level: str, message: str):
        color = LEVEL_COLORS.get(level)
        stamp = f'<span style="color:#7a7a7a">{datetime.now():%H:%M:%S}</span> '
        for line in message.splitlines() or [""]:
            text = html.escape(line).replace(" ", "&nbsp;")
            if color:
                text = f'<span style="color:{color}">{text}</span>'
            self.view.appendHtml(stamp + text)
            stamp = '<span style="color:#7a7a7a">' + "&nbsp;" * 9 + "</span>"

    def _job_started(self, reporter, title):
        reporter.signals.log.connect(self.append, QUEUED)
        reporter.signals.progress.connect(self._progress, QUEUED)
        self.append("info", f"▶ {title}")
        self.stop_button.setEnabled(True)
        self.stop_button.setText(tr("Dừng"))
        self.progress_label.setText(title)

    def _job_finished(self, title, ok, cancelled, message):
        self.stop_button.setEnabled(False)
        self.progress.hide()
        self.progress_label.setText("")
        if message:
            self.append("warning" if cancelled else "error", message)
        if ok:
            self.append("info", tr("✔ {title}: xong", title=title))
        elif cancelled:
            self.append("warning", tr("■ {title}: đã dừng", title=title))
        else:
            self.append("error", tr("✖ {title}: lỗi", title=title))

    def _progress(self, desc, current, total):
        self.progress_label.setText(desc)
        self.progress.show()
        if total < 0:
            self.progress.setRange(0, 0)
        else:
            self.progress.setRange(0, max(total, 1))
            self.progress.setValue(current)
            self.progress.setFormat(f"{current}/{total}")

    def _stop(self):
        self.jobs.cancel()
        self.stop_button.setEnabled(False)
        self.stop_button.setText(tr("Đang dừng…"))


def open_path(path):
    """Open a file or folder with its Windows default application."""
    os.startfile(str(path))
