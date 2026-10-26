import sys
from pathlib import Path

PROJECT_TEMPLATE_NAME = "VNXXXXXXX_TEMPLATE"


def resource_root() -> Path:
    """Folder holding template/, dms/ and projects/VNXXXXXXX_TEMPLATE.

    In development this is the repository root; in a PyInstaller build the same
    folders are bundled next to the executable's extracted files (sys._MEIPASS).
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[2]


def template_mdd() -> Path:
    return resource_root() / "template" / "TemplateProject.mdd"


def output_ddf_dms() -> Path:
    return resource_root() / "dms" / "OutputDDFFile.dms"


def project_template_dir() -> Path:
    return resource_root() / "projects" / PROJECT_TEMPLATE_NAME


def default_workspace() -> Path:
    if getattr(sys, "frozen", False):
        # The install folder is read-only; the GUI lets the user pick another workspace.
        return Path.home() / "Documents" / "iField" / "projects"
    return resource_root() / "projects"
