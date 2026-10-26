from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings, Qt
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMainWindow, QMessageBox, QPushButton, QSplitter, QTabWidget,
                               QVBoxLayout, QWidget)

from app import __version__
from app.core import paths
from app.core.env_check import check_environment
from app.core.pipeline import run_pipeline
from app.core.project import Project
from app.gui.codebook_page import CodebookPage
from app.gui import i18n
from app.gui.config_page import ClickOnlyComboBox, ConfigPage
from app.gui.i18n import tr
from app.gui.jobs import JobManager
from app.gui.log_panel import LogPanel, open_path
from app.gui.run_page import RunPage
from app.gui.sidebar import Sidebar
from app.gui.spss_page import SpssPage


class MainWindow(QMainWindow):
    # The window on screen: switching the language replaces it with a new one.
    current: "MainWindow | None" = None

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"iField Data Processing {__version__}")
        self.resize(1280, 860)
        self.settings = QSettings("iField", "DataProcessing")
        self.jobs = JobManager(self)
        self.project: Project | None = None

        # --- Left: projects
        self.sidebar = Sidebar()
        self.sidebar.setMinimumWidth(220)

        # --- Right: header + tabs + log
        self.title = QLabel(tr("Chọn một project"))
        self.title.setStyleSheet("font-size: 18px; font-weight: 600;")
        self.subtitle = QLabel("")
        self.subtitle.setStyleSheet("color: #7a7a7a;")
        self.subtitle.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.open_folder = QPushButton(tr("Mở thư mục project"))
        self.open_folder.clicked.connect(lambda: self.project and open_path(self.project.root))

        titles = QVBoxLayout()
        titles.setSpacing(0)
        titles.addWidget(self.title)
        titles.addWidget(self.subtitle)
        header = QHBoxLayout()
        header.addLayout(titles, stretch=1)
        header.addWidget(self.open_folder)
        self.language_combo = ClickOnlyComboBox()
        self.language_combo.setToolTip(tr("Ngôn ngữ giao diện"))
        for code, name in i18n.LANGUAGES.items():
            self.language_combo.addItem(name, code)
        self.language_combo.setCurrentIndex(self.language_combo.findData(i18n.language()))
        self.language_combo.currentIndexChanged.connect(self._change_language)
        header.addWidget(self.language_combo)

        self.config_page = ConfigPage(self.jobs)
        self.run_page = RunPage(self.jobs)
        self.spss_page = SpssPage(self.jobs, self.settings)
        self.codebook_page = CodebookPage(self.jobs)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.config_page, tr("Cấu hình"))
        self.tabs.addTab(self.run_page, tr("Chạy xử lý"))
        self.tabs.addTab(self.spss_page, tr("Xuất SPSS"))
        self.tabs.addTab(self.codebook_page, tr("Codebook OE"))
        self.tabs.currentChanged.connect(self._tab_changed)

        self.log_panel = LogPanel(self.jobs)

        top = QWidget()
        top_layout = QVBoxLayout(top)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addLayout(header)
        top_layout.addWidget(self.tabs)

        self.right_splitter = QSplitter(Qt.Orientation.Vertical)
        self.right_splitter.addWidget(top)
        self.right_splitter.addWidget(self.log_panel)
        self.right_splitter.setStretchFactor(0, 3)
        self.right_splitter.setStretchFactor(1, 1)

        self.main_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.main_splitter.addWidget(self.sidebar)
        self.main_splitter.addWidget(self.right_splitter)
        self.main_splitter.setStretchFactor(1, 1)
        self.main_splitter.setSizes([260, 1020])

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(12, 12, 12, 8)
        layout.addWidget(self.main_splitter)
        self.setCentralWidget(central)

        # --- Wiring
        self.sidebar.project_selected.connect(self.set_project)
        self.sidebar.workspace_changed.connect(lambda ws: self.settings.setValue("workspace", str(ws)))
        self.config_page.config_changed.connect(self.run_page.show_plan)
        self.config_page.dirty_changed.connect(self._dirty_changed)
        self.run_page.run_requested.connect(self.run_pipeline)
        self.jobs.busy_changed.connect(self._busy_changed)

        self._restore_state()
        self.jobs.start(tr("Kiểm tra môi trường"), lambda reporter: check_environment(),
                        on_success=self.sidebar.set_environment, exclusive=False)

    # --- Project ---------------------------------------------------------------------

    def set_project(self, project: Project | None):
        self._confirm_unsaved(can_cancel=False)

        self.project = project
        self.title.setText(project.name if project else tr("Chọn một project"))
        self.subtitle.setText(str(project.root) if project else "")
        self.open_folder.setEnabled(project is not None)
        self.tabs.setEnabled(project is not None)
        for page in (self.config_page, self.run_page, self.spss_page, self.codebook_page):
            page.set_project(project)
        if project is not None:
            self.settings.setValue("project", project.name)

    def run_pipeline(self):
        if self.project is None:
            return
        if self.config_page.dirty and not self.config_page.save():
            return
        project = self.project
        reporter = self.jobs.start(tr("Chạy xử lý {name}", name=project.name), lambda reporter: run_pipeline(project, reporter),
                                   on_success=lambda _: self._pipeline_finished(True, False, ""),
                                   on_failure=lambda message, cancelled: self._pipeline_finished(False, cancelled, message))
        if reporter is not None:
            self.run_page.attach(reporter)

    def _pipeline_finished(self, ok, cancelled, message):
        self.run_page.finished(ok, cancelled, message)
        self.spss_page.refresh_files()

    # --- State -----------------------------------------------------------------------

    def _tab_changed(self, index):
        if self.tabs.widget(index) is self.run_page:
            self.run_page.refresh_outputs()
        elif self.tabs.widget(index) is self.spss_page and not self.jobs.busy:
            self.spss_page.refresh_files()

    def _dirty_changed(self, dirty):
        self.tabs.setTabText(0, tr("Cấu hình •") if dirty else tr("Cấu hình"))
        self.run_page.set_unsaved(dirty)

    def _busy_changed(self, busy):
        self.sidebar.set_locked(busy)

    def _restore_state(self):
        geometry = self.settings.value("geometry")
        if isinstance(geometry, QByteArray):
            self.restoreGeometry(geometry)
        for key, splitter in (("main_splitter", self.main_splitter), ("right_splitter", self.right_splitter)):
            state = self.settings.value(key)
            if isinstance(state, QByteArray):
                splitter.restoreState(state)

        workspace = Path(self.settings.value("workspace", str(paths.default_workspace())))
        workspace.mkdir(parents=True, exist_ok=True)
        self.sidebar.set_workspace(workspace, select=self.settings.value("project"))
        self.tabs.setCurrentIndex(int(self.settings.value("tab", 0) or 0))

    def _save_state(self):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("main_splitter", self.main_splitter.saveState())
        self.settings.setValue("right_splitter", self.right_splitter.saveState())
        self.settings.setValue("tab", self.tabs.currentIndex())

    def _confirm_unsaved(self, can_cancel: bool) -> bool:
        """Offer to save an edited configuration; False when the user cancels."""
        if not (self.config_page.dirty and self.project is not None):
            return True
        buttons = QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard
        if can_cancel:
            buttons |= QMessageBox.StandardButton.Cancel
        answer = QMessageBox.question(self, tr("Cấu hình chưa lưu"),
                                      tr("Lưu thay đổi cấu hình của {name}?", name=self.project.name), buttons)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            self.config_page.save()
        return True

    # --- Language --------------------------------------------------------------------

    def _change_language(self, index):
        code = self.language_combo.itemData(index)
        if code == i18n.language():
            return
        # Background jobs report to this window's widgets: they must be over before it goes away.
        if self.jobs.active:
            QMessageBox.information(self, tr("Đang chạy"), tr("Một tác vụ đang chạy. Hãy chờ tác vụ kết thúc rồi đổi ngôn ngữ."))
            self._reset_language_combo()
            return
        if not self._confirm_unsaved(can_cancel=True):
            self._reset_language_combo()
            return

        i18n.set_language(code)
        self.settings.setValue("language", code)
        self._save_state()
        # Same project, tab, size and position: the new window reads them from the settings.
        MainWindow.current = MainWindow()
        MainWindow.current.show()
        self._replaced = True
        self.close()
        self.deleteLater()

    def _reset_language_combo(self):
        self.language_combo.blockSignals(True)
        self.language_combo.setCurrentIndex(self.language_combo.findData(i18n.language()))
        self.language_combo.blockSignals(False)

    def closeEvent(self, event):
        if getattr(self, "_replaced", False):
            event.accept()
            return
        if self.jobs.busy:
            QMessageBox.information(self, tr("Đang chạy"),
                                    tr("Một tác vụ đang chạy. Bấm \"Dừng\" và chờ tác vụ kết thúc trước khi thoát."))
            event.ignore()
            return
        if not self._confirm_unsaved(can_cancel=True):
            event.ignore()
            return
        self._save_state()
        event.accept()
