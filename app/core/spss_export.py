"""MDD/DDF -> SPSS .sav export (formerly spss_processing.py)."""
from pathlib import Path

import app.core  # noqa: F401  (collections aliases needed by savReaderWriter)
from app.core.env_check import com_initialized
from app.core.errors import SourceError
from app.core.project import Project
from app.core.reporter import ConsoleReporter, Reporter


def _resolve(project: Project, path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else project.root / path


def list_mdd_fields(mdd_file: Path) -> list[str]:
    """Top-level field names of an MDD, to let the user pick the questions to export."""
    import win32com.client as w32

    with com_initialized():
        mdm = w32.Dispatch("MDM.Document")
        mdm.Open(str(mdd_file))
        try:
            return [f.Name for f in mdm.Fields]
        finally:
            mdm.Close()


def export_spss(project: Project, mdd_file, ddf_file, questions=(), sql_query: str = "SELECT * FROM VDATA",
                reporter: Reporter | None = None) -> Path:
    """Write <mdd name>_SPSS.sav next to the MDD. An empty `questions` exports every visible field.

    mdd_file/ddf_file may be absolute or relative to the project folder (e.g. "data\\X_EXPORT.mdd").
    """
    from object.spss import SPSSObject

    reporter = reporter or ConsoleReporter()
    for path in (mdd_file, ddf_file):
        if not _resolve(project, path).is_file():
            raise SourceError(f"File not found: {_resolve(project, path)}")

    with com_initialized(), project.working_directory(), reporter.capture_stdout():
        reporter.info(f"Exporting {mdd_file} to SPSS ({len(questions) or 'all'} questions)")
        spss = SPSSObject(str(mdd_file), str(ddf_file), sql_query, list(questions))
        spss.to_spss()

    output = _resolve(project, str(mdd_file).replace(".mdd", "_SPSS.sav"))
    reporter.info(f"Saved {output}")
    return output
