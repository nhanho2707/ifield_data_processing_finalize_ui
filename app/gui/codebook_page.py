"""Map manual OE coding labels to codebook codes."""
from pathlib import Path

import pandas as pd
from PySide6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout, QWidget)

from app.core.codebook import apply_codebook
from app.core.project import Project
from app.gui.i18n import tr
from app.gui.jobs import JobManager
from app.gui.log_panel import open_path


def _select(combo: QComboBox, items, preferred: str):
    current = combo.currentText()
    combo.clear()
    combo.addItems(items)
    for candidate in (current, preferred):
        if candidate in items:
            combo.setCurrentText(candidate)
            return


class CodebookPage(QWidget):
    def __init__(self, jobs: JobManager, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.project: Project | None = None
        self._last_output: Path | None = None

        self.file_edit = QLineEdit()
        self.file_edit.setReadOnly(True)
        self.file_edit.setPlaceholderText("File *_manual_report.xlsx")
        browse = QPushButton(tr("Chọn…"))
        browse.clicked.connect(self._browse)
        file_row = QHBoxLayout()
        file_row.addWidget(self.file_edit, stretch=1)
        file_row.addWidget(browse)

        self.overview_sheet = QComboBox()
        self.overview_sheet.currentTextChanged.connect(self._load_columns)
        self.punch_sheet = QComboBox()
        self.code_column = QComboBox()
        self.label_column = QComboBox()
        self.label_column.setToolTip(tr("Nhãn ghi vào kết quả cùng với mã"))
        self.match_column = QComboBox()
        self.match_column.setToolTip(tr("Nội dung được tìm trong các cột label_<n> của sheet punch (không phân biệt hoa thường)"))
        self.respondent_column = QLineEdit("RESPONDENTID")

        source = QGroupBox(tr("File coding"))
        form = QFormLayout(source)
        form.addRow(tr("File Excel"), file_row)
        form.addRow(tr("Sheet codebook"), self.overview_sheet)
        form.addRow(tr("Sheet punch"), self.punch_sheet)
        form.addRow(tr("Cột mã"), self.code_column)
        form.addRow(tr("Cột nhãn kết quả"), self.label_column)
        form.addRow(tr("Cột dùng để so khớp"), self.match_column)
        form.addRow(tr("Cột ID đáp viên"), self.respondent_column)

        hint = QLabel('<span style="color:#7a7a7a">' + tr(
            'Với mỗi cột label_&lt;n&gt; của sheet punch, thêm cột label_&lt;n&gt;_ipsos = (mã, nhãn) của dòng codebook '
            'đầu tiên có nội dung "cột so khớp" nằm trong nhãn đã code. Kết quả lưu thành &lt;tên file&gt;_coding.xlsx cùng thư mục.')
            + '</span>')
        hint.setWordWrap(True)

        self.run_button = QPushButton(tr("Tạo file coding"))
        self.run_button.setMinimumHeight(34)
        self.run_button.setStyleSheet("font-weight: 600; padding: 0 18px;")
        self.run_button.clicked.connect(self.run)
        self.result_label = QLabel("")
        self.open_button = QPushButton(tr("Mở file"))
        self.open_button.hide()
        self.open_button.clicked.connect(lambda: self._last_output and open_path(self._last_output))

        bottom = QHBoxLayout()
        bottom.addWidget(self.run_button)
        bottom.addWidget(self.result_label, stretch=1)
        bottom.addWidget(self.open_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(source)
        layout.addWidget(hint)
        layout.addStretch()
        layout.addLayout(bottom)

        jobs.busy_changed.connect(self._update_buttons)
        self._update_buttons()

    def set_project(self, project: Project | None):
        self.project = project

    def _browse(self):
        start = ""
        if self.project is not None:
            oe_dir = self.project.data_dir / "oe"
            start = str(oe_dir if oe_dir.is_dir() else self.project.data_dir)
        path, _ = QFileDialog.getOpenFileName(self, tr("Chọn file coding"), start, "Excel (*.xlsx)")
        if path:
            self.set_file(Path(path))

    def set_file(self, path: Path):
        self.file_edit.setText(str(path))
        self.result_label.setText("")
        self.open_button.hide()
        try:
            sheets = pd.ExcelFile(path, engine="openpyxl").sheet_names
        except Exception as ex:
            self.result_label.setText(tr("✖ Không đọc được file: {error}", error=ex))
            sheets = []
        _select(self.punch_sheet, sheets, "manual_Code_Punch")
        _select(self.overview_sheet, sheets, "manual_Code_Overview")
        self._update_buttons()

    def _load_columns(self, sheet):
        columns = []
        if sheet and self.file_edit.text():
            try:
                columns = [str(c) for c in pd.read_excel(self.file_edit.text(), engine="openpyxl", sheet_name=sheet, nrows=0).columns]
            except Exception:
                columns = []
        _select(self.code_column, columns, "CODE")
        _select(self.label_column, columns, "LABEL VNI")
        _select(self.match_column, columns, "TACTIC LABEL")
        self._update_buttons()

    def run(self):
        excel = Path(self.file_edit.text())
        options = dict(
            label_column=self.label_column.currentText(), match_column=self.match_column.currentText(),
            code_column=self.code_column.currentText(), overview_sheet=self.overview_sheet.currentText(),
            punch_sheet=self.punch_sheet.currentText(), respondent_column=self.respondent_column.text().strip(),
        )
        self.result_label.setStyleSheet("")
        self.result_label.setText(tr("Đang chạy…"))
        self.open_button.hide()

        def done(output: Path):
            self._last_output = output
            self.result_label.setStyleSheet("color: #107c10;")
            self.result_label.setText(tr("✔ Đã lưu {name}", name=output.name))
            self.open_button.show()

        def failed(message, cancelled):
            self.result_label.setStyleSheet("color: #d13438;")
            self.result_label.setText(tr("✖ Lỗi, xem nhật ký bên dưới"))

        self.jobs.start(f"Codebook {excel.name}", lambda reporter: apply_codebook(excel, reporter=reporter, **options),
                        on_success=done, on_failure=failed)

    def _update_buttons(self, *_):
        ready = bool(self.file_edit.text()) and bool(self.match_column.currentText()) and not self.jobs.busy
        self.run_button.setEnabled(ready)
