import struct
from contextlib import contextmanager

from app.core.config_model import Issue

# COM components of IBM SPSS Data Collection / Unicom used by the `object` package.
REQUIRED_PROG_IDS = {
    "MDM.Document": "Metadata Document Model",
    "DMOM.Job": "Data Management Object Model",
    "ADODB.Connection": "ADO",
}


def python_bits() -> int:
    return struct.calcsize("P") * 8


@contextmanager
def com_initialized():
    """COM must be initialised in every thread that uses it (a GUI runs jobs in a worker thread)."""
    import pythoncom

    pythoncom.CoInitialize()
    try:
        yield
    finally:
        pythoncom.CoUninitialize()


def check_environment(require_spss: bool = False) -> list[Issue]:
    issues = []

    try:
        import win32com.client as w32
    except ImportError:
        return [Issue("error", "pywin32 is not installed.")]

    with com_initialized():
        for prog_id, label in REQUIRED_PROG_IDS.items():
            try:
                w32.Dispatch(prog_id)
            except Exception:
                issues.append(Issue(
                    "error",
                    f"COM component {prog_id} ({label}) is not available. Install IBM SPSS Data Collection "
                    f"(the same {python_bits()}-bit version as this application).",
                ))

    try:
        import app.core  # noqa: F401  (collections aliases needed by savReaderWriter)
        import savReaderWriter  # noqa: F401
    except Exception as ex:
        issues.append(Issue("error" if require_spss else "warning", f"SPSS export unavailable (savReaderWriter: {ex})."))

    return issues
