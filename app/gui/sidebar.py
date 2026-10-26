from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
                               QListWidgetItem, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from app.core.errors import IFieldError
from app.core.project import Project, create_project, list_projects
from app.gui.i18n import tr


class Sidebar(QWidget):
    project_selected = Signal(object)   # Project | None
    workspace_changed = Signal(object)  # Path

    def __init__(self, parent=None):
        super().__init__(parent)
        self.workspace: Path | None = None

        title = QLabel("PROJECTS")
        title.setStyleSheet("font-weight: 600; color: #7a7a7a; letter-spacing: 1px;")
        self.workspace_label = QLabel("")
        self.workspace_label.setWordWrap(True)
        self.workspace_label.setStyleSheet("color: #7a7a7a;")
        change = QPushButton(tr("Đổi…"))
        change.setToolTip(tr("Chọn thư mục chứa các project"))
        change.clicked.connect(self._choose_workspace)
        workspace_row = QHBoxLayout()
        workspace_row.addWidget(self.workspace_label, stretch=1)
        workspace_row.addWidget(change, alignment=Qt.AlignmentFlag.AlignTop)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Tìm project…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._filter)

        self.list = QListWidget()
        self.list.currentItemChanged.connect(self._selected)

        self.new_button = QPushButton(tr("+  Tạo project mới"))
        self.new_button.clicked.connect(self._new_project)
        refresh = QPushButton(tr("Làm mới"))
        refresh.clicked.connect(lambda: self.reload(self.current_name()))
        buttons = QHBoxLayout()
        buttons.addWidget(self.new_button, stretch=1)
        buttons.addWidget(refresh)

        self.env_label = QLabel(tr("● Đang kiểm tra Data Collection…"))
        self.env_label.setWordWrap(True)
        self.env_label.setStyleSheet("color: #7a7a7a;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title)
        layout.addLayout(workspace_row)
        layout.addWidget(self.search)
        layout.addWidget(self.list, stretch=1)
        layout.addLayout(buttons)
        layout.addWidget(self.env_label)

    def set_workspace(self, workspace: Path, select: str | None = None):
        self.workspace = Path(workspace)
        parts = self.workspace.parts
        self.workspace_label.setText(str(self.workspace) if len(parts) <= 3 else "…\\" + "\\".join(parts[-2:]))
        self.workspace_label.setToolTip(str(self.workspace))
        self.reload(select)

    def reload(self, select: str | None = None):
        self.list.blockSignals(True)
        self.list.clear()
        for project in list_projects(self.workspace) if self.workspace else []:
            item = QListWidgetItem(project.name)
            item.setData(Qt.ItemDataRole.UserRole, project)
            item.setToolTip(str(project.root))
            self.list.addItem(item)
        self.list.blockSignals(False)
        self._filter(self.search.text())

        matches = self.list.findItems(select, Qt.MatchFlag.MatchExactly) if select else []
        if matches:
            self.list.setCurrentItem(matches[0])
        else:
            self.list.setCurrentItem(None)
            self.project_selected.emit(None)

    def current_name(self) -> str | None:
        item = self.list.currentItem()
        return item.text() if item else None

    def set_locked(self, locked: bool):
        """Switching project while a job runs would change the data under it."""
        self.list.setEnabled(not locked)
        self.new_button.setEnabled(not locked)

    def set_environment(self, issues):
        errors = [i for i in issues if i.level == "error"]
        if errors:
            self.env_label.setText(tr("● Data Collection: thiếu thành phần"))
            self.env_label.setStyleSheet("color: #d13438;")
        else:
            self.env_label.setText(tr("● Data Collection: sẵn sàng"))
            self.env_label.setStyleSheet("color: #107c10;")
        self.env_label.setToolTip("\n".join(i.message for i in issues) or tr("Đủ các thành phần COM cần thiết."))

    def _filter(self, text):
        text = text.strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(text) and text not in item.text().lower())

    def _selected(self, current, _previous):
        self.project_selected.emit(current.data(Qt.ItemDataRole.UserRole) if current else None)

    def _choose_workspace(self):
        path = QFileDialog.getExistingDirectory(self, tr("Chọn thư mục chứa các project"), str(self.workspace or ""))
        if path:
            self.set_workspace(Path(path))
            self.workspace_changed.emit(self.workspace)

    def _new_project(self):
        if self.workspace is None:
            return
        name, ok = QInputDialog.getText(self, tr("Tạo project mới"), tr("Tên project (vd. VN2026100_ABC):"))
        if not ok or not name.strip():
            return
        try:
            self.workspace.mkdir(parents=True, exist_ok=True)
            project: Project = create_project(self.workspace, name)
        except (IFieldError, OSError) as ex:
            QMessageBox.warning(self, tr("Không tạo được project"), str(ex))
            return
        self.reload(project.name)
        QMessageBox.information(self, tr("Đã tạo project"),
                                tr("Đã tạo {path}\n\nChép file CSV vào source\\csv và file XML vào source\\xml, "
                                   "sau đó bấm \"Quét lại\" và \"Tự điền\" trong tab Cấu hình.", path=project.root))
