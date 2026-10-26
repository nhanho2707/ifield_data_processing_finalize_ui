"""Form editor for config.json."""
import copy
import json
import re

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFormLayout,
                               QGridLayout, QGroupBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from app.core.config_model import Issue, has_errors, load_config, save_config, validate_config, xml_mappings
from app.core.errors import IFieldError
from app.core.pipeline import check_update_file
from app.core.preflight import preflight, scan_sources
from app.core.project import Project
from app.gui.i18n import tr
from app.gui.jobs import JobManager

MAIN = "main"
NOT_USED = ""
XML_PROTO_ID = re.compile(r"ProtoSurvey_(\d+)_", re.IGNORECASE)


class ClickOnlyComboBox(QComboBox):
    """Combo box changed only by opening its list: the mouse wheel scrolls the page instead."""

    def wheelEvent(self, event):
        event.ignore()

# (config path, label, tooltip)
OPTIONS = [
    (("run_mdd_source",), "Tạo lại file MDD/DDF từ XML",
     "run_mdd_source: xoá các file MDD/DDF/IVS/XLSX trong data rồi dựng lại từ XML."),
    (("run_mdd_export_source",), "Chỉ tạo lại file _EXPORT từ MDD có sẵn",
     "run_mdd_export_source: dùng khi run_mdd_source tắt."),
    (("source_initialization", "delete_all"), "Xoá toàn bộ dữ liệu cũ trước khi nạp",
     "delete_all: DELETE FROM VDATA trước khi nạp dữ liệu."),
    (("source_initialization", "dummy_data_required"), "Chỉ nạp dữ liệu test (_DefaultSP)",
     "dummy_data_required: bật = CHỈ nạp phiếu test; tắt = bỏ phiếu test."),
    (("source_initialization", "remove_all_ids"), "Xoá phiếu huỷ / phiếu thừa",
     "remove_all_ids: xoá các phiếu có _LoaiPhieu khác {_1,_5}."),
    (("processing_data", "run_ce_source"), "Chạy làm sạch dữ liệu (CE)",
     "run_ce_source: chạy dms\\CLEAN_DATA_SCRIPT.dms, tạo file _CE."),
    (("processing_data", "run_oe_source"), "Chạy xử lý câu mở (OE)",
     "run_oe_source: chạy dms\\CLEAN_DATA_PROCESSING.dms, tạo file _OE."),
]


def _get(config, path):
    for key in path:
        config = config.get(key, {}) if isinstance(config, dict) else {}
    return bool(config) if not isinstance(config, dict) else False


def _set(config, path, value):
    for key in path[:-1]:
        config = config.setdefault(key, {})
    config[path[-1]] = value


def _full_check(project, config):
    """preflight, plus update_data.csv against the existing _EXPORT MDD."""
    issues, scan = preflight(project, config)
    if scan is not None:
        try:
            issues += check_update_file(project, config, scan)
        except Exception as ex:
            issues.append(Issue("error", f"update_data.csv could not be checked: {ex}"))
    return issues, scan


def _proto_sort_key(pid):
    return (0, int(pid)) if str(pid).isdigit() else (1, str(pid))


class JsonDialog(QDialog):
    def __init__(self, config, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Sửa config.json"))
        self.resize(760, 640)
        self.result_config = None

        self.editor = QPlainTextEdit(json.dumps(config, ensure_ascii=False, indent=4))
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(tr("Dùng cho các mục nâng cao (cột thông tin đáp viên, axis_expression...). "
                                   "Thay đổi chỉ được ghi khi bấm Lưu.")))
        layout.addWidget(self.editor)
        layout.addWidget(buttons)

    def _accept(self):
        try:
            config = json.loads(self.editor.toPlainText())
        except json.JSONDecodeError as ex:
            QMessageBox.warning(self, tr("JSON không hợp lệ"),
                                tr("Dòng {line}, cột {column}: {message}", line=ex.lineno, column=ex.colno, message=ex.msg))
            return
        if not isinstance(config, dict):
            QMessageBox.warning(self, tr("JSON không hợp lệ"), tr("Nội dung phải là một object { ... }."))
            return
        self.result_config = config
        self.accept()


class ConfigPage(QWidget):
    config_changed = Signal(dict)   # live form content (unsaved)
    dirty_changed = Signal(bool)
    saved = Signal()

    def __init__(self, jobs: JobManager, parent=None):
        super().__init__(parent)
        self.jobs = jobs
        self.project: Project | None = None
        self._config: dict = {}
        self._baseline: dict = {}
        self._stage_ids: list[str] = []
        self._row_counts: dict[int, int] | None = None
        self._xml_files: list[str] = []
        self._loading = False
        self._dirty = False

        # --- General
        self.name_edit = QLineEdit()
        self.language_combo = ClickOnlyComboBox()
        self.language_combo.setEditable(True)
        self.language_combo.addItems(["VIT", "ENU"])
        general = QGroupBox(tr("Thông tin chung"))
        form = QFormLayout(general)
        form.addRow(tr("Tên project (project_name)"), self.name_edit)
        form.addRow(tr("Ngôn ngữ mặc định"), self.language_combo)

        # --- Sources
        self.sources_summary = QLabel("")
        rescan = QPushButton(tr("Quét lại"))
        rescan.setToolTip(tr("Đọc lại source\\csv và source\\xml"))
        rescan.clicked.connect(self.rescan)
        autofill = QPushButton(tr("Tự điền"))
        autofill.setToolTip(tr("Ghép XML theo ProtoID trong tên file, đưa vào phần main và chọn ProtoID lớn nhất làm final."))
        autofill.clicked.connect(self.autofill)
        add_stage = QPushButton(tr("Thêm stage"))
        add_stage.clicked.connect(self.add_stage)
        remove_stage = QPushButton(tr("Xoá stage cuối"))
        remove_stage.clicked.connect(self.remove_stage)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["ProtoID", tr("Số dòng CSV"), tr("File XML"), tr("Phần"), "Final"])
        self.table.verticalHeader().hide()
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.table.horizontalHeader()
        for col, mode in enumerate([QHeaderView.ResizeMode.ResizeToContents, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.ResizeToContents,
                                    QHeaderView.ResizeMode.ResizeToContents]):
            header.setSectionResizeMode(col, mode)
        self.table.setMinimumHeight(160)

        sources = QGroupBox(tr("Nguồn dữ liệu (ProtoID trong CSV ↔ file XML)"))
        tools = QHBoxLayout()
        tools.addWidget(self.sources_summary)
        tools.addStretch()
        for button in (rescan, autofill, add_stage, remove_stage):
            tools.addWidget(button)
        sources_layout = QVBoxLayout(sources)
        sources_layout.addLayout(tools)
        sources_layout.addWidget(self.table)
        sources_layout.addWidget(QLabel('<span style="color:#7a7a7a">' + tr(
            "Final: phiên bản XML dùng để dựng MDD của phần đó. Các stage follow-up được nạp vào vòng lặp Phase.") + '</span>'))

        # --- Options
        self.option_boxes = {}
        options = QGroupBox(tr("Tuỳ chọn xử lý"))
        grid = QGridLayout(options)
        for i, (path, label, tip) in enumerate(OPTIONS):
            box = QCheckBox(tr(label))
            box.setToolTip(tr(tip))
            box.toggled.connect(self._changed)
            self.option_boxes[path] = box
            grid.addWidget(box, i // 2, i % 2)
        self.option_boxes[("run_mdd_source",)].toggled.connect(self._sync_option_states)

        # --- Check result
        self.issues = QListWidget()
        self.issues.setMinimumHeight(70)
        self.issues.setMaximumHeight(140)
        self.issues_title = QLabel(tr("Kiểm tra"))
        self.issues_title.setStyleSheet("font-weight: 600;")

        # --- Buttons
        self.json_button = QPushButton(tr("Sửa JSON…"))
        self.json_button.clicked.connect(self.edit_json)
        self.revert_button = QPushButton(tr("Hoàn tác"))
        self.revert_button.clicked.connect(self.revert)
        self.check_button = QPushButton(tr("Kiểm tra"))
        self.check_button.setToolTip(tr("Kiểm tra config, file nguồn và môi trường Data Collection mà không xử lý gì."))
        self.check_button.clicked.connect(self.check)
        self.save_button = QPushButton(tr("Lưu"))
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self.save)

        buttons = QHBoxLayout()
        buttons.addWidget(self.json_button)
        buttons.addStretch()
        buttons.addWidget(self.revert_button)
        buttons.addWidget(self.check_button)
        buttons.addWidget(self.save_button)

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.addWidget(general)
        content_layout.addWidget(sources, stretch=1)
        content_layout.addWidget(options)
        content_layout.addWidget(self.issues_title)
        content_layout.addWidget(self.issues)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setWidget(content)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(scroll)
        layout.addLayout(buttons)

        self.name_edit.textChanged.connect(self._changed)
        self.language_combo.currentTextChanged.connect(self._changed)
        jobs.busy_changed.connect(lambda busy: self.check_button.setEnabled(not busy))
        self._update_buttons()

    # --- Loading ---------------------------------------------------------------------

    def set_project(self, project: Project | None):
        self.project = project
        self.issues.clear()
        if project is None:
            return
        try:
            config = load_config(project.config_path)
        except IFieldError as ex:
            QMessageBox.warning(self, tr("Không đọc được config.json"), str(ex))
            config = {}
        self._load(config, counts=None)
        self.rescan()

    def _load(self, config: dict, counts):
        self._config = copy.deepcopy(config)
        self._row_counts = counts
        self._stage_ids = list(config.get("stages", {}).keys())
        self._xml_files = sorted(p.name for p in self.project.xml_dir.glob("*.xml")) if self.project else []

        self._loading = True
        self.name_edit.setText(str(config.get("project_name", "")))
        self.language_combo.setCurrentText(str(config.get("source_initialization", {}).get("default_language", "VIT")))
        for path, box in self.option_boxes.items():
            box.setChecked(_get(config, path))
        self._fill_table(self._entries_from_config(config))
        self._loading = False

        self._sync_option_states()
        self._baseline = self.form_config()
        self._set_dirty(False)
        self.config_changed.emit(self._baseline)

    def _entries_from_config(self, config):
        """[(proto_id, xml, section, final)] for the configured rows followed by the unconfigured ones."""
        entries = {}
        sections = [(MAIN, config.get("main", {}))] + list(config.get("stages", {}).items())
        for section, data in sections:
            final = str(data.get("protoid_final", ""))
            for pid, xml in xml_mappings(data):
                entries[pid] = (pid, xml, section, pid == final)
        return self._with_unconfigured(list(entries.values()))

    def _xml_by_proto(self) -> dict[str, str]:
        """ProtoID -> XML file, from names like ProtoSurvey_12319_{...}.xml."""
        by_id = {}
        for xml in self._xml_files:
            match = XML_PROTO_ID.search(xml)
            if match:
                by_id[match.group(1)] = xml
        return by_id

    def _with_unconfigured(self, entries):
        """Add a row (not used yet) for every ProtoID of the CSV or of an XML file name missing from entries.

        Its XML is pre-selected from the file name carrying the same ProtoID.
        """
        by_id = self._xml_by_proto()
        known = {e[0] for e in entries}
        missing = {str(pid) for pid in self._row_counts or {}} | set(by_id)
        return entries + [(pid, by_id.get(pid, ""), NOT_USED, False)
                          for pid in sorted(missing - known, key=_proto_sort_key)]

    # --- Table -----------------------------------------------------------------------

    def _fill_table(self, entries):
        self.table.setRowCount(0)
        self.table.setRowCount(len(entries))
        for row, (pid, xml, section, final) in enumerate(entries):
            id_item = QTableWidgetItem(pid)
            id_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.table.setItem(row, 0, id_item)

            count_item = QTableWidgetItem("…" if self._row_counts is None else str(self._row_counts.get(int(pid), 0)) if pid.isdigit() else "?")
            count_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            count_item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            if self._row_counts is not None and pid.isdigit() and int(pid) not in self._row_counts:
                count_item.setForeground(QColor("#d13438"))
                count_item.setToolTip(tr("ProtoID này không có dữ liệu trong CSV"))
            self.table.setItem(row, 1, count_item)

            xml_combo = ClickOnlyComboBox()
            xml_combo.addItem("")
            xml_combo.addItems(self._xml_files)
            if xml and xml not in self._xml_files:
                xml_combo.addItem(xml)
                xml_combo.setItemData(xml_combo.count() - 1, QColor("#d13438"), Qt.ItemDataRole.ForegroundRole)
            xml_combo.setCurrentText(xml)
            xml_combo.currentIndexChanged.connect(lambda _, r=row: self._xml_changed(r))
            self.table.setCellWidget(row, 2, xml_combo)

            section_combo = ClickOnlyComboBox()
            self._fill_sections(section_combo, section)
            section_combo.currentIndexChanged.connect(lambda _, r=row: self._section_changed(r))
            self.table.setCellWidget(row, 3, section_combo)

            final_box = QCheckBox()
            final_box.setChecked(final)
            final_box.setEnabled(section != NOT_USED)
            final_box.toggled.connect(lambda checked, r=row: self._final_toggled(r, checked))
            holder = QWidget()
            holder_layout = QHBoxLayout(holder)
            holder_layout.setContentsMargins(0, 0, 0, 0)
            holder_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
            holder_layout.addWidget(final_box)
            self.table.setCellWidget(row, 4, holder)

        self._update_summary()

    def _fill_sections(self, combo: QComboBox, current: str):
        combo.blockSignals(True)
        combo.clear()
        combo.addItem(tr("— Không dùng —"), NOT_USED)
        combo.addItem("Main", MAIN)
        for stage_id in self._stage_ids:
            combo.addItem(stage_id, stage_id)
        index = combo.findData(current)
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.blockSignals(False)

    def _xml_changed(self, row):
        """The ProtoID of a row follows the XML chosen for it (ProtoSurvey_12319_{...}.xml -> 12319)."""
        entries = self._entries()
        pid, xml, section, final = entries[row]
        match = XML_PROTO_ID.search(xml)
        if self._loading or not match or match.group(1) == pid:
            self._changed()
            return
        new_pid = match.group(1)
        entries[row] = (new_pid, xml, section, final)
        # The row takes over that ProtoID: drop its other row; the previous ProtoID comes back unused.
        entries = [e for r, e in enumerate(entries) if r == row or e[0] != new_pid]
        # Rebuilt after the signal: the table must not delete the combo box emitting it.
        QTimer.singleShot(0, lambda: self._refill_table(entries))

    def _refill_table(self, entries):
        scroll = self.table.verticalScrollBar().value()
        self._loading = True
        self._fill_table(self._with_unconfigured(entries))
        self._loading = False
        self.table.verticalScrollBar().setValue(scroll)
        self._changed()

    def _final_box(self, row) -> QCheckBox:
        return self.table.cellWidget(row, 4).findChild(QCheckBox)

    def _row_state(self, row):
        return (
            self.table.item(row, 0).text(),
            self.table.cellWidget(row, 2).currentText(),
            self.table.cellWidget(row, 3).currentData(),
            self._final_box(row).isChecked(),
        )

    def _entries(self):
        return [self._row_state(row) for row in range(self.table.rowCount())]

    def _section_changed(self, row):
        section = self.table.cellWidget(row, 3).currentData()
        box = self._final_box(row)
        box.blockSignals(True)
        box.setEnabled(section != NOT_USED)
        # The first row put in a section becomes its final version.
        others_final = any(s == section and f for r, (_, _, s, f) in enumerate(self._entries()) if r != row)
        box.setChecked(section != NOT_USED and not others_final)
        box.blockSignals(False)
        self._changed()

    def _final_toggled(self, row, checked):
        if checked:
            section = self.table.cellWidget(row, 3).currentData()
            for other in range(self.table.rowCount()):
                if other != row and self.table.cellWidget(other, 3).currentData() == section:
                    box = self._final_box(other)
                    box.blockSignals(True)
                    box.setChecked(False)
                    box.blockSignals(False)
        self._changed()

    def _update_summary(self):
        if self._row_counts is None:
            self.sources_summary.setText(tr("Đang đọc CSV…"))
        else:
            self.sources_summary.setText(tr("{protos} ProtoID trong CSV · {rows} dòng · {xmls} file XML", protos=len(self._row_counts),
                                            rows=sum(self._row_counts.values()), xmls=len(self._xml_files)))

    # --- Actions ---------------------------------------------------------------------

    def rescan(self):
        if self.project is None:
            return
        project = self.project
        self._row_counts = None
        self._update_summary()

        def done(result):
            scan, issues = result
            if project != self.project:
                return
            dirty = self._dirty
            self._row_counts = scan.proto_rows
            self._xml_files = sorted(p.name for p in project.xml_dir.glob("*.xml"))
            self._loading = True
            self._fill_table(self._with_unconfigured(self._entries()))
            self._loading = False
            self._set_dirty(dirty)
            for issue in issues:
                self._add_issue(issue.level, issue.message)

        self.jobs.start(tr("Đọc file CSV"), lambda reporter: scan_sources(project), on_success=done,
                        on_failure=lambda message, _: self._add_issue("error", message), exclusive=False)

    def autofill(self):
        entries = self._entries()
        by_id = self._xml_by_proto()

        self._loading = True
        for row, (pid, xml, section, _) in enumerate(entries):
            if not xml and pid in by_id:
                self.table.cellWidget(row, 2).setCurrentText(by_id[pid])
                xml = by_id[pid]
            if xml and section == NOT_USED:
                combo = self.table.cellWidget(row, 3)
                combo.blockSignals(True)
                combo.setCurrentIndex(combo.findData(MAIN))
                combo.blockSignals(False)
                self._final_box(row).setEnabled(True)
        entries = self._entries()
        main_rows = [r for r, e in enumerate(entries) if e[2] == MAIN]
        if main_rows and not any(entries[r][3] for r in main_rows):
            latest = max(main_rows, key=lambda r: _proto_sort_key(entries[r][0]))
            self._final_box(latest).setChecked(True)
        self._loading = False
        self._changed()

    def add_stage(self):
        self._stage_ids.append(f"stage-{len(self._stage_ids) + 1}")
        self._refresh_section_combos()

    def remove_stage(self):
        if not self._stage_ids:
            return
        stage_id = self._stage_ids[-1]
        if any(section == stage_id for _, _, section, _ in self._entries()):
            QMessageBox.information(self, tr("Không xoá được"),
                                    tr("Còn ProtoID đang gán cho {stage}. Hãy bỏ gán trước.", stage=stage_id))
            return
        self._stage_ids.pop()
        self._refresh_section_combos()

    def _refresh_section_combos(self):
        for row in range(self.table.rowCount()):
            combo = self.table.cellWidget(row, 3)
            self._fill_sections(combo, combo.currentData())
        self._changed()

    def edit_json(self):
        dialog = JsonDialog(self.form_config(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            baseline = self._baseline
            self._load(dialog.result_config, counts=self._row_counts)
            self._baseline = baseline
            self._changed()

    def revert(self):
        if self.project is not None:
            self._load(load_config(self.project.config_path), counts=self._row_counts)

    def save(self) -> bool:
        if self.project is None:
            return False
        config = self.form_config()
        try:
            save_config(self.project.config_path, config)
        except OSError as ex:
            QMessageBox.warning(self, tr("Không lưu được"), str(ex))
            return False
        self._config = copy.deepcopy(config)
        self._baseline = config
        self._set_dirty(False)
        self.issues.clear()
        for issue in validate_config(config):
            self._add_issue(issue.level, issue.message)
        self.saved.emit()
        return True

    def check(self):
        if self.project is None:
            return
        project, config = self.project, self.form_config()
        self.issues.clear()
        self.issues_title.setText(tr("Kiểm tra: đang chạy…"))

        def done(result):
            issues, _ = result
            for issue in issues:
                self._add_issue(issue.level, issue.message)
            if has_errors(issues):
                self.issues_title.setText(tr("Kiểm tra: {count} lỗi", count=sum(i.level == "error" for i in issues)))
            else:
                self.issues_title.setText(tr("Kiểm tra: sẵn sàng chạy (có cảnh báo)") if issues else tr("Kiểm tra: sẵn sàng chạy"))
                if not issues:
                    self._add_issue("ok", tr("Không có lỗi."))

        self.jobs.start(tr("Kiểm tra {name}", name=project.name), lambda reporter: _full_check(project, config), on_success=done,
                        on_failure=lambda message, _: self.issues_title.setText(tr("Kiểm tra: lỗi")))

    # --- State -----------------------------------------------------------------------

    def form_config(self) -> dict:
        config = copy.deepcopy(self._config)
        config["project_name"] = self.name_edit.text().strip()
        _set(config, ("source_initialization", "default_language"), self.language_combo.currentText().strip())
        for path, box in self.option_boxes.items():
            _set(config, path, box.isChecked())

        main = {"xmls": {}, "protoid_final": ""}
        stages = {stage_id: {"xmls": {}, "protoid_final": ""} for stage_id in self._stage_ids}
        for pid, xml, section, final in self._entries():
            if section == NOT_USED or not xml:
                continue
            target = main if section == MAIN else stages[section]
            target["xmls"][pid] = xml
            if final:
                target["protoid_final"] = pid
        config["main"] = main
        config["stages"] = stages
        return config

    @property
    def dirty(self) -> bool:
        return self._dirty

    def _changed(self, *_):
        if self._loading or self.project is None:
            return
        config = self.form_config()
        self._set_dirty(config != self._baseline)
        self.config_changed.emit(config)

    def _set_dirty(self, dirty: bool):
        if dirty != self._dirty:
            self._dirty = dirty
            self.dirty_changed.emit(dirty)
        self._update_buttons()

    def _update_buttons(self):
        self.save_button.setEnabled(self._dirty)
        self.revert_button.setEnabled(self._dirty)

    def _sync_option_states(self):
        self.option_boxes[("run_mdd_export_source",)].setEnabled(not self.option_boxes[("run_mdd_source",)].isChecked())

    def _add_issue(self, level, message):
        item = QListWidgetItem({"error": "✖ ", "warning": "⚠ ", "ok": "✔ "}.get(level, "") + message)
        item.setForeground(QColor({"error": "#d13438", "warning": "#c97a00", "ok": "#107c10"}.get(level, "#000000")))
        self.issues.addItem(item)
