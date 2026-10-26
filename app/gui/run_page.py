"""Run the processing pipeline and browse its output files."""
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QGroupBox, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from app.core.pipeline import STEPS
from app.core.project import Project
from app.gui.i18n import tr
from app.gui.jobs import QUEUED, JobManager
from app.gui.log_panel import open_path

STEP_LABELS = {
    "load_sources": "Đọc file CSV / XML",
    "build_mdd": "Tạo file MDD/DDF",
    "check_updates": "Kiểm tra update_data.csv",
    "insert_main": "Nạp dữ liệu phần main",
    "export_respondents": "Xuất thông tin đáp viên (RESPONDENT.xlsx)",
    "insert_stages": "Nạp dữ liệu các stage follow-up",
    "apply_updates": "Áp dụng update_data.csv",
    "remove_ids": "Xoá phiếu huỷ / phiếu thừa",
    "clean_ce": "Làm sạch dữ liệu (CE)",
    "clean_oe": "Xử lý câu mở (OE)",
}

STATUS = {
    "pending": ("○", "Chờ", None),
    "off": ("·", "Tắt trong cấu hình", "#9a9a9a"),
    "running": ("▶", "Đang chạy…", "#0f6cbd"),
    "done": ("✔", "Xong", "#107c10"),
    "skipped": ("–", "Bỏ qua (không có dữ liệu)", "#9a9a9a"),
    "failed": ("✖", "Lỗi", "#d13438"),
    "cancelled": ("■", "Đã dừng", "#c97a00"),
}


def _size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024


class RunPage(QWidget):
    run_requested = Signal()

    def __init__(self, jobs: JobManager, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.project: Project | None = None
        self._config: dict = {}
        self._plan: dict[str, str] = {}
        self._started = datetime.now()

        self.run_button = QPushButton(tr("▶  Chạy xử lý"))
        self.run_button.setMinimumHeight(34)
        self.run_button.setStyleSheet("font-weight: 600; padding: 0 18px;")
        self.run_button.clicked.connect(self.run_requested)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        self.unsaved_label = QLabel("")
        self.unsaved_label.setStyleSheet("color: #c97a00;")

        self.steps = QTreeWidget()
        self.steps.setHeaderLabels([tr("Bước"), tr("Trạng thái"), tr("Thời gian")])
        self.steps.setRootIsDecorated(False)
        self.steps.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.steps.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.steps.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._items = {}
        for step in STEPS:
            item = QTreeWidgetItem([tr(STEP_LABELS.get(step.key, step.title)), "", ""])
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight)
            self.steps.addTopLevelItem(item)
            self._items[step.key] = item

        steps_box = QGroupBox(tr("Các bước (bật/tắt trong tab Cấu hình)"))
        steps_layout = QVBoxLayout(steps_box)
        steps_layout.addWidget(self.steps)

        self.outputs = QTreeWidget()
        self.outputs.setHeaderLabels([tr("File trong data"), tr("Kích thước"), tr("Sửa lúc")])
        self.outputs.setRootIsDecorated(False)
        self.outputs.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.outputs.itemDoubleClicked.connect(lambda item: open_path(item.data(0, Qt.ItemDataRole.UserRole)))
        open_data = QPushButton(tr("Mở thư mục data"))
        open_data.clicked.connect(lambda: self.project and open_path(self.project.data_dir))
        self.open_log = QPushButton(tr("Mở log gần nhất"))
        self.open_log.clicked.connect(self._open_latest_log)
        refresh = QPushButton(tr("Làm mới"))
        refresh.clicked.connect(self.refresh_outputs)

        outputs_box = QGroupBox(tr("Kết quả (nháy đúp để mở)"))
        outputs_layout = QVBoxLayout(outputs_box)
        outputs_layout.addWidget(self.outputs)
        outputs_buttons = QHBoxLayout()
        outputs_buttons.addWidget(open_data)
        outputs_buttons.addWidget(self.open_log)
        outputs_buttons.addStretch()
        outputs_buttons.addWidget(refresh)
        outputs_layout.addLayout(outputs_buttons)

        top = QHBoxLayout()
        top.addWidget(self.run_button)
        top.addWidget(self.status_label, stretch=1)
        top.addWidget(self.unsaved_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addWidget(steps_box, stretch=1)
        layout.addWidget(outputs_box, stretch=1)

        jobs.busy_changed.connect(lambda busy: self.run_button.setEnabled(not busy and self.project is not None))

    def set_project(self, project: Project | None):
        self.project = project
        self.status_label.setText("")
        self.run_button.setEnabled(project is not None and not self.jobs.busy)
        self.refresh_outputs()

    def show_plan(self, config: dict):
        """Mark the steps disabled by the (possibly unsaved) configuration."""
        self._config = config
        self._plan = {}
        for step in STEPS:
            try:
                enabled = bool(step.enabled_by_config(config))
            except (KeyError, TypeError):
                enabled = True
            self._plan[step.key] = "pending" if enabled else "off"
            self._set_status(step.key, self._plan[step.key])

    def set_unsaved(self, dirty: bool):
        self.unsaved_label.setText(tr("Cấu hình chưa lưu: sẽ tự lưu khi chạy") if dirty else "")

    def attach(self, reporter):
        """Follow the steps of a pipeline job that is starting."""
        self.show_plan(self._config)
        self._started = datetime.now()
        self.status_label.setStyleSheet("")
        self.status_label.setText(tr("Đang chạy…"))
        reporter.signals.step.connect(self._on_step, QUEUED)

    def finished(self, ok: bool, cancelled: bool, message: str = ""):
        elapsed = datetime.now() - self._started
        minutes, seconds = divmod(int(elapsed.total_seconds()), 60)
        if ok:
            self.status_label.setStyleSheet("color: #107c10;")
            self.status_label.setText(tr("✔ Hoàn tất sau {minutes}m{seconds}s", minutes=minutes, seconds=f"{seconds:02d}"))
        elif cancelled:
            self.status_label.setStyleSheet("color: #c97a00;")
            self.status_label.setText(tr("■ Đã dừng"))
        else:
            self.status_label.setStyleSheet("color: #d13438;")
            self.status_label.setText("✖ " + (message.strip().splitlines() or [tr("Lỗi")])[-1][:300])
        self.refresh_outputs()

    def _on_step(self, key, title, status, elapsed, error):
        if status == "skipped" and self._plan.get(key) == "off":
            status = "off"
        self._set_status(key, status, elapsed if status in ("done", "failed", "cancelled") else None)
        if error:
            self._items[key].setToolTip(1, error)

    def _set_status(self, key, status, elapsed=None):
        item = self._items.get(key)
        if item is None:
            return
        icon, text, color = STATUS[status]
        item.setText(1, f"{icon}  {tr(text)}")
        item.setText(2, "" if elapsed is None else f"{elapsed:.1f}s")
        item.setToolTip(1, "")
        brush = QColor(color) if color else self.palette().text().color()
        for col in range(3):
            item.setForeground(col, brush)

    def refresh_outputs(self):
        self.outputs.clear()
        if self.project is None or not self.project.data_dir.is_dir():
            return
        files = sorted((p for p in self.project.data_dir.iterdir() if p.is_file() and p.name != "README.md"),
                       key=lambda p: p.stat().st_mtime, reverse=True)
        for path in files:
            stat = path.stat()
            item = QTreeWidgetItem([path.name, _size(stat.st_size), f"{datetime.fromtimestamp(stat.st_mtime):%d/%m/%Y %H:%M}"])
            item.setData(0, Qt.ItemDataRole.UserRole, str(path))
            item.setTextAlignment(1, Qt.AlignmentFlag.AlignRight)
            self.outputs.addTopLevelItem(item)

    def _open_latest_log(self):
        if self.project is None:
            return
        logs = sorted(self.project.logs_dir.glob("*.log"), key=lambda p: p.stat().st_mtime)
        if logs:
            open_path(logs[-1])
