"""Export an MDD/DDF to SPSS with a question picker."""
from pathlib import Path

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout,
                               QWidget)

from app.core.project import Project
from app.core.spss_export import export_spss, list_mdd_fields
from app.gui.i18n import tr
from app.gui.jobs import JobManager
from app.gui.log_panel import open_path

# Most processed files first.
_SUFFIX_ORDER = ("_OE", "_CE", "_EXPORT")


def _mdd_sort_key(path: Path):
    for i, suffix in enumerate(_SUFFIX_ORDER):
        if path.stem.upper().endswith(suffix):
            return (i, path.name)
    return (len(_SUFFIX_ORDER), path.name)


class SpssPage(QWidget):
    def __init__(self, jobs: JobManager, settings: QSettings, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.settings = settings
        self.project: Project | None = None
        self._last_output: Path | None = None

        self.mdd_combo = QComboBox()
        self.mdd_combo.currentIndexChanged.connect(self._mdd_changed)
        browse = QPushButton(tr("Chọn file khác…"))
        browse.clicked.connect(self._browse)
        self.ddf_label = QLabel("")
        self.load_button = QPushButton(tr("Tải danh sách câu hỏi"))
        self.load_button.clicked.connect(self.load_questions)

        mdd_row = QHBoxLayout()
        mdd_row.addWidget(self.mdd_combo, stretch=1)
        mdd_row.addWidget(browse)
        mdd_row.addWidget(self.load_button)

        self.sql_edit = QLineEdit("SELECT * FROM VDATA")
        self.sql_edit.setToolTip(tr("Ví dụ: SELECT * FROM VDATA WHERE Respondent_serial = '6823050106491224'"))

        source = QGroupBox(tr("Nguồn"))
        form = QFormLayout(source)
        form.addRow(tr("File MDD"), mdd_row)
        form.addRow(tr("File DDF"), self.ddf_label)
        form.addRow(tr("Câu truy vấn"), self.sql_edit)

        self.filter_edit = QLineEdit()
        self.filter_edit.setPlaceholderText(tr("Lọc câu hỏi…"))
        self.filter_edit.textChanged.connect(self._apply_filter)
        select_all = QPushButton(tr("Chọn tất cả (đang hiện)"))
        select_all.clicked.connect(lambda: self._check_visible(True))
        select_none = QPushButton(tr("Bỏ chọn tất cả"))
        select_none.clicked.connect(lambda: self._check_all(False))
        paste = QPushButton(tr("Dán danh sách…"))
        paste.setToolTip(tr("Dán tên câu hỏi, mỗi dòng một câu (vd. copy từ danh sách cũ trong spss_processing.py)"))
        paste.clicked.connect(self._paste)

        self.questions = QListWidget()
        self.questions.itemChanged.connect(self._update_count)
        self.count_label = QLabel("")

        tools = QHBoxLayout()
        tools.addWidget(self.filter_edit, stretch=1)
        tools.addWidget(select_all)
        tools.addWidget(select_none)
        tools.addWidget(paste)

        questions_box = QGroupBox(tr("Câu hỏi xuất ra SPSS (thứ tự theo MDD)"))
        questions_layout = QVBoxLayout(questions_box)
        questions_layout.addLayout(tools)
        questions_layout.addWidget(self.questions)
        questions_layout.addWidget(self.count_label)

        self.export_button = QPushButton(tr("Xuất SPSS (.sav)"))
        self.export_button.setMinimumHeight(34)
        self.export_button.setStyleSheet("font-weight: 600; padding: 0 18px;")
        self.export_button.clicked.connect(self.export)
        self.result_label = QLabel("")
        self.open_button = QPushButton(tr("Mở thư mục"))
        self.open_button.hide()
        self.open_button.clicked.connect(lambda: self._last_output and open_path(self._last_output.parent))

        bottom = QHBoxLayout()
        bottom.addWidget(self.export_button)
        bottom.addWidget(self.result_label, stretch=1)
        bottom.addWidget(self.open_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(source)
        layout.addWidget(questions_box, stretch=1)
        layout.addLayout(bottom)

        jobs.busy_changed.connect(self._update_buttons)
        self._update_buttons()

    # --- Project / files -------------------------------------------------------------

    def set_project(self, project: Project | None):
        self.project = project
        self.result_label.setText("")
        self.open_button.hide()
        self.refresh_files()

    def refresh_files(self):
        current = self.mdd_combo.currentData()
        self.mdd_combo.blockSignals(True)
        self.mdd_combo.clear()
        if self.project is not None and self.project.data_dir.is_dir():
            for path in sorted(self.project.data_dir.glob("*.mdd"), key=_mdd_sort_key):
                self.mdd_combo.addItem(path.name, str(path))
        if current:
            index = self.mdd_combo.findData(current)
            if index >= 0:
                self.mdd_combo.setCurrentIndex(index)
        self.mdd_combo.blockSignals(False)
        self._mdd_changed()

    def _browse(self):
        start = str(self.project.data_dir) if self.project else ""
        path, _ = QFileDialog.getOpenFileName(self, tr("Chọn file MDD"), start, "Metadata (*.mdd)")
        if path:
            path = str(Path(path))
            if self.mdd_combo.findData(path) < 0:
                self.mdd_combo.addItem(Path(path).name, path)
            self.mdd_combo.setCurrentIndex(self.mdd_combo.findData(path))

    def _mdd_path(self) -> Path | None:
        data = self.mdd_combo.currentData()
        return Path(data) if data else None

    def _mdd_changed(self, *_):
        self.questions.clear()
        mdd = self._mdd_path()
        if mdd is None:
            self.ddf_label.setText("")
        else:
            ddf = mdd.with_suffix(".ddf")
            self.ddf_label.setText(ddf.name if ddf.is_file() else '<span style="color:#d13438">' + tr("{name} không tồn tại", name=ddf.name) + '</span>')
        self._update_count()
        self._update_buttons()

    # --- Questions -------------------------------------------------------------------

    def _settings_key(self, mdd: Path) -> str:
        return f"spss/{mdd}".replace("\\", "/")

    def load_questions(self):
        mdd = self._mdd_path()
        if mdd is None:
            return

        def done(names):
            if mdd != self._mdd_path():
                return
            saved = set(self.settings.value(self._settings_key(mdd), [], type=list) or [])
            self.questions.blockSignals(True)
            self.questions.clear()
            for name in names:
                item = QListWidgetItem(name)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if name in saved else Qt.CheckState.Unchecked)
                self.questions.addItem(item)
            self.questions.blockSignals(False)
            self._apply_filter(self.filter_edit.text())
            self._update_count()

        self.jobs.start(tr("Đọc danh sách câu hỏi {name}", name=mdd.name), lambda reporter: list_mdd_fields(mdd), on_success=done)

    def _items(self):
        return [self.questions.item(i) for i in range(self.questions.count())]

    def _checked(self) -> list[str]:
        return [item.text() for item in self._items() if item.checkState() == Qt.CheckState.Checked]

    def _apply_filter(self, text):
        text = text.strip().lower()
        for item in self._items():
            item.setHidden(bool(text) and text not in item.text().lower())

    def _check_visible(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for item in self._items():
            if not item.isHidden():
                item.setCheckState(state)

    def _check_all(self, checked):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for item in self._items():
            item.setCheckState(state)

    def _paste(self):
        if not self.questions.count():
            QMessageBox.information(self, tr("Chưa có danh sách"), tr("Bấm \"Tải danh sách câu hỏi\" trước."))
            return
        text, ok = QInputDialog.getMultiLineText(self, tr("Dán danh sách câu hỏi"), tr("Mỗi dòng một tên câu hỏi:"))
        if not ok:
            return
        wanted = [w.strip().strip('",') for w in text.splitlines() if w.strip().strip('",')]
        by_name = {item.text().lower(): item for item in self._items()}
        missing = []
        for name in wanted:
            item = by_name.get(name.lower())
            if item is None:
                missing.append(name)
            else:
                item.setCheckState(Qt.CheckState.Checked)
        if missing:
            QMessageBox.warning(self, tr("Không tìm thấy"), tr("Các câu hỏi sau không có trong MDD:\n") + "\n".join(missing[:50]))

    def _update_count(self, *_):
        total = self.questions.count()
        checked = len(self._checked())
        self.count_label.setText(tr("Đã chọn {checked}/{total}", checked=checked, total=total)
                                 + (tr(" — không chọn câu nào = xuất toàn bộ") if total and not checked else ""))

    # --- Export ----------------------------------------------------------------------

    def export(self):
        mdd = self._mdd_path()
        if self.project is None or mdd is None:
            return
        ddf = mdd.with_suffix(".ddf")
        questions = self._checked()
        if not questions and QMessageBox.question(
                self, tr("Xuất toàn bộ?"), tr("Chưa chọn câu hỏi nào. Xuất tất cả các câu hỏi không bị ẩn?")) != QMessageBox.StandardButton.Yes:
            return
        self.settings.setValue(self._settings_key(mdd), questions)

        project, sql = self.project, self.sql_edit.text().strip() or "SELECT * FROM VDATA"
        self.result_label.setStyleSheet("")
        self.result_label.setText(tr("Đang xuất…"))
        self.open_button.hide()

        def done(output: Path):
            self._last_output = output
            self.result_label.setStyleSheet("color: #107c10;")
            self.result_label.setText(tr("✔ Đã lưu {name}", name=output.name))
            self.open_button.show()

        def failed(message, cancelled):
            self.result_label.setStyleSheet("color: #d13438;")
            self.result_label.setText(tr("■ Đã dừng") if cancelled else tr("✖ Lỗi, xem nhật ký bên dưới"))

        self.jobs.start(tr("Xuất SPSS {name}", name=mdd.name), lambda reporter: export_spss(project, mdd, ddf, questions, sql, reporter),
                        on_success=done, on_failure=failed)

    def _update_buttons(self, *_):
        ready = self.project is not None and self._mdd_path() is not None and not self.jobs.busy
        self.export_button.setEnabled(ready and self._mdd_path().with_suffix(".ddf").is_file())
        self.load_button.setEnabled(ready)
