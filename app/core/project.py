import os
import shutil
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from app.core import paths
from app.core.config_model import load_config, save_config
from app.core.errors import ConfigError

# The DMS scripts resolve `#include "dms\..."` and write their side files relative to
# the current directory, so a job must run with the project folder as cwd. The cwd is
# process-wide, hence one job at a time.
_cwd_lock = threading.Lock()


@dataclass(frozen=True)
class Project:
    root: Path

    @property
    def name(self) -> str:
        return self.root.name

    @property
    def config_path(self) -> Path:
        return self.root / "config.json"

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def csv_dir(self) -> Path:
        return self.root / "source" / "csv"

    @property
    def xml_dir(self) -> Path:
        return self.root / "source" / "xml"

    @property
    def update_data_csv(self) -> Path:
        return self.root / "source" / "update_data.csv"

    @property
    def dms_dir(self) -> Path:
        return self.root / "dms"

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    def load_config(self) -> dict:
        return load_config(self.config_path)

    @contextmanager
    def working_directory(self):
        with _cwd_lock:
            previous = os.getcwd()
            os.chdir(self.root)
            try:
                yield self.root
            finally:
                os.chdir(previous)

    def remove_data_files(self, patterns):
        for pattern in patterns:
            for f in self.data_dir.glob(pattern):
                if f.is_file():
                    f.unlink()


def open_project(workspace: Path, name: str) -> Project:
    project = Project(Path(workspace).resolve() / name)
    if not project.config_path.is_file():
        raise ConfigError(f"Project not found (no config.json): {project.root}")
    return project


def list_projects(workspace: Path) -> list[Project]:
    workspace = Path(workspace)
    if not workspace.is_dir():
        return []
    return sorted(
        (Project(d.resolve()) for d in workspace.iterdir()
         if d.is_dir() and d.name != paths.PROJECT_TEMPLATE_NAME and (d / "config.json").is_file()),
        key=lambda p: p.name,
    )


def create_project(workspace: Path, name: str) -> Project:
    """Create a new project folder from projects/VNXXXXXXX_TEMPLATE."""
    name = name.strip()
    if not name or any(c in name for c in '\\/:*?"<>|'):
        raise ConfigError(f'Invalid project name: "{name}"')

    project = Project(Path(workspace).resolve() / name)
    if project.root.exists():
        raise ConfigError(f"Project already exists: {project.root}")

    shutil.copytree(paths.project_template_dir(), project.root)

    config = load_config(project.config_path)
    config["project_name"] = name
    save_config(project.config_path, config)
    return project
