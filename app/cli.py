"""Command line front-end for the core.

    python -m app list
    python -m app new VN2025100_ABC
    python -m app check VN2025100_ABC
    python -m app run VN2025100_ABC
    python -m app spss VN2025100_ABC --mdd data\\X_EXPORT.mdd --ddf data\\X_EXPORT.ddf -q Q1 Q2
    python -m app codebook "projects\\VN2025100_ABC\\data\\oe\\Q9 manual_report.xlsx"
"""
import argparse
import sys
from pathlib import Path

import app.core  # noqa: F401  (must run before savReaderWriter is imported)
from app import __version__
from app.core import paths
from app.core.config_model import has_errors
from app.core.errors import IFieldError
from app.core.project import create_project, list_projects, open_project
from app.core.reporter import ConsoleReporter


def _cmd_list(args):
    for project in list_projects(args.workspace):
        print(project.name)
    return 0


def _cmd_new(args):
    project = create_project(args.workspace, args.name)
    print(f"Created {project.root}")
    return 0


def _cmd_check(args):
    from app.core.preflight import preflight

    project = open_project(args.workspace, args.project)
    issues, scan = preflight(project, project.load_config())

    if scan is not None:
        print(f"{len(scan.csv_files)} CSV files in source\\csv")
        for proto_id, rows in sorted(scan.proto_rows.items()):
            print(f"  ProtoID {proto_id}: {rows} rows")
    for issue in issues:
        print(issue)

    if has_errors(issues):
        return 2
    print("OK: ready to run.")
    return 0


def _cmd_run(args):
    from app.core.pipeline import run_pipeline

    project = open_project(args.workspace, args.project)
    results = run_pipeline(project, ConsoleReporter())
    print(f"\nFinished: {sum(r.status == 'done' for r in results)} steps done, "
          f"{sum(r.status == 'skipped' for r in results)} skipped.")
    return 0


def _cmd_spss(args):
    from app.core.spss_export import export_spss

    project = open_project(args.workspace, args.project)
    questions = list(args.questions or [])
    if args.questions_file:
        questions += [line.strip() for line in Path(args.questions_file).read_text(encoding="utf-8").splitlines() if line.strip()]
    export_spss(project, args.mdd, args.ddf, questions, args.sql, ConsoleReporter())
    return 0


def _cmd_codebook(args):
    from app.core.codebook import apply_codebook

    apply_codebook(Path(args.excel), label_column=args.label_column, match_column=args.match_column,
                   reporter=ConsoleReporter())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ifield", description="iField data processing")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--workspace", type=Path, default=paths.default_workspace(),
                        help="folder containing the projects (default: %(default)s)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("list", help="list the projects of the workspace")
    p.set_defaults(func=_cmd_list)

    p = sub.add_parser("new", help="create a project from VNXXXXXXX_TEMPLATE")
    p.add_argument("name")
    p.set_defaults(func=_cmd_new)

    p = sub.add_parser("check", help="check config.json and source files without processing anything")
    p.add_argument("project")
    p.set_defaults(func=_cmd_check)

    p = sub.add_parser("run", help="run the processing pipeline of a project")
    p.add_argument("project")
    p.set_defaults(func=_cmd_run)

    p = sub.add_parser("spss", help="export an MDD/DDF to SPSS .sav")
    p.add_argument("project")
    p.add_argument("--mdd", required=True, help="path relative to the project folder, e.g. data\\X_EXPORT.mdd")
    p.add_argument("--ddf", required=True)
    p.add_argument("-q", "--questions", nargs="*", help="questions to export (default: all)")
    p.add_argument("--questions-file", help="text file with one question name per line")
    p.add_argument("--sql", default="SELECT * FROM VDATA")
    p.set_defaults(func=_cmd_spss)

    p = sub.add_parser("codebook", help="map manual OE labels to codebook codes")
    p.add_argument("excel", help="the *_manual_report.xlsx file")
    p.add_argument("--label-column", default="LABEL VNI")
    p.add_argument("--match-column", default="TACTIC LABEL")
    p.set_defaults(func=_cmd_codebook)

    return parser


def main(argv=None) -> int:
    # Vietnamese labels/messages must not crash a legacy (cp1252) console.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="replace")

    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except IFieldError as ex:
        print(f"\n[ERROR] {ex}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
