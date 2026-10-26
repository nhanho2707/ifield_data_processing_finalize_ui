import os
import sys
import tempfile
import traceback
from pathlib import Path


def self_test(report_path: Path) -> int:
    """Check an installation without opening the window: `"iField Data Processing.exe" --self-test report.txt`."""
    lines, failed = [], False

    def check(name, fn):
        nonlocal failed
        try:
            detail = fn()
            lines.append(f"OK    {name}" + (f": {detail}" if detail else ""))
        except Exception:
            failed = True
            lines.append(f"FAIL  {name}\n{traceback.format_exc()}")

    def environment():
        from app.core.env_check import check_environment
        issues = check_environment(require_spss=True)
        if any(i.level == "error" for i in issues):
            raise RuntimeError("; ".join(i.message for i in issues))
        return f"{len(issues)} warnings" if issues else ""

    def resources():
        from app.core import paths
        for path in (paths.template_mdd(), paths.output_ddf_dms(), paths.project_template_dir() / "config.json"):
            if not path.is_file():
                raise FileNotFoundError(path)
        return str(paths.resource_root())

    def spss_io():
        import savReaderWriter
        with tempfile.TemporaryDirectory() as tmp:
            sav = os.path.join(tmp, "test.sav")
            with savReaderWriter.SavWriter(sav, [b"v1"], {b"v1": 0}, ioUtf8=True) as writer:
                writer.writerow([1.0])
            return f"{os.path.getsize(sav)} bytes written"

    def excel_io():
        import pandas as pd
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test.xlsx")
            with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
                pd.DataFrame({"CODE": [1], "LABEL VNI": ["Có"]}).to_excel(writer, sheet_name="s", index=False)
            df = pd.read_excel(path, engine="openpyxl", sheet_name="s")
            if df.iloc[0, 1] != "Có":
                raise ValueError(df)
            return ""

    def gui():
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        import app.gui.main_window  # noqa: F401
        QApplication.instance() or QApplication([])
        return ""

    import app.core  # noqa: F401
    check("Data Collection + savReaderWriter", environment)
    check("Bundled resources", resources)
    check("SPSS I/O DLLs", spss_io)
    check("Excel I/O", excel_io)
    check("Qt GUI", gui)
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if failed else 0


def main() -> int:
    # A windowed executable has no console: give print()/tqdm somewhere to write.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    # `"iField Data Processing.exe" --cli run <project>`: the command line commands without a window
    # (e.g. for scheduled runs; output goes to the project's logs folder).
    if len(sys.argv) > 1 and sys.argv[1] == "--cli":
        from app.cli import main as cli_main
        return cli_main(sys.argv[2:])

    if "--self-test" in sys.argv:
        index = sys.argv.index("--self-test")
        report = Path(sys.argv[index + 1]) if len(sys.argv) > index + 1 else Path("self_test.txt")
        return self_test(report)

    import app.core  # noqa: F401  (collections aliases needed by savReaderWriter)
    from PySide6.QtWidgets import QApplication

    from app.gui.main_window import MainWindow

    from PySide6.QtGui import QIcon

    application = QApplication(sys.argv)
    application.setApplicationName("iField Data Processing")
    application.setOrganizationName("iField")
    application.setWindowIcon(QIcon(str(Path(__file__).with_name("app.ico"))))

    from PySide6.QtCore import QSettings

    from app.gui import i18n
    i18n.set_language(QSettings("iField", "DataProcessing").value("language", i18n.DEFAULT))

    MainWindow.current = MainWindow()
    MainWindow.current.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
