import os
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app.core import paths
from app.core.config_model import Issue, validate_config, xml_mappings
from app.core.env_check import check_environment
from app.core.project import Project


@dataclass
class SourceScan:
    """Which ProtoSurveyIDs appear in which CSV files of source/csv."""
    csv_files: list[Path] = field(default_factory=list)
    proto_files: dict[int, list[Path]] = field(default_factory=dict)
    proto_rows: dict[int, int] = field(default_factory=dict)


def scan_sources(project: Project) -> tuple[SourceScan, list[Issue]]:
    scan = SourceScan()
    issues = []

    # Oldest file first: data from newer exports is inserted last.
    scan.csv_files = sorted(project.csv_dir.glob("*.csv"), key=os.path.getctime)

    for csv_file in scan.csv_files:
        try:
            df = pd.read_csv(csv_file, encoding="utf-8", usecols=["ProtoSurveyID"], low_memory=False)
        except ValueError:
            issues.append(Issue("error", f"{csv_file.name}: column ProtoSurveyID not found."))
            continue
        except Exception as ex:
            issues.append(Issue("error", f"{csv_file.name}: cannot be read ({ex})."))
            continue

        for proto_id, rows in df["ProtoSurveyID"].value_counts(sort=False).sort_index().items():
            proto_id = int(proto_id)
            scan.proto_files.setdefault(proto_id, []).append(csv_file)
            scan.proto_rows[proto_id] = scan.proto_rows.get(proto_id, 0) + int(rows)

    return scan, issues


def check_sources(project: Project, config: dict, scan: SourceScan) -> list[Issue]:
    issues = []

    def error(message):
        issues.append(Issue("error", message))

    if not scan.csv_files:
        error(f"No CSV file in {project.csv_dir}.")

    sections = [("main", config["main"])] + [(f"stages.{k}", v) for k, v in config["stages"].items()]
    configured_ids = set()

    for section_name, section in sections:
        for proto_id, xml_file in xml_mappings(section):
            if not (project.xml_dir / xml_file).is_file():
                error(f"{section_name}: XML file not found: source\\xml\\{xml_file}")
            try:
                configured_ids.add(int(proto_id))
            except ValueError:
                continue  # already reported by validate_config
            if scan.csv_files and int(proto_id) not in scan.proto_files:
                error(f"{section_name}: ProtoID {proto_id} has no data in the CSV files.")

    for proto_id, files in scan.proto_files.items():
        if proto_id not in configured_ids:
            issues.append(Issue(
                "warning",
                f"ProtoID {proto_id} has {scan.proto_rows[proto_id]} rows in {', '.join(f.name for f in files)} "
                f"but no XML in config.json; inserting those rows will fail.",
            ))

    if not project.update_data_csv.is_file():
        error("source\\update_data.csv not found (it may contain only the header row).")

    name = config["project_name"]
    data = project.data_dir

    if config["run_mdd_source"]:
        if not paths.template_mdd().is_file():
            error(f"Template MDD not found: {paths.template_mdd()}")
        if not paths.output_ddf_dms().is_file():
            error(f"DMS file not found: {paths.output_ddf_dms()}")
    elif config["run_mdd_export_source"]:
        if not (data / f"{name}.mdd").is_file():
            error(f"run_mdd_source is false and run_mdd_export_source is true but data\\{name}.mdd does not exist.")
    elif not ((data / f"{name}_EXPORT.mdd").is_file() and (data / f"{name}_EXPORT.ddf").is_file()):
        error(f"run_mdd_source is false but data\\{name}_EXPORT.mdd/.ddf do not exist.")

    processing = config["processing_data"]
    if processing["run_ce_source"] and not (project.dms_dir / "CLEAN_DATA_SCRIPT.dms").is_file():
        error("dms\\CLEAN_DATA_SCRIPT.dms not found.")
    if processing["run_oe_source"]:
        if not (project.dms_dir / "CLEAN_DATA_PROCESSING.dms").is_file():
            error("dms\\CLEAN_DATA_PROCESSING.dms not found.")
        if not processing["run_ce_source"] and not (data / f"{name}_CE.mdd").is_file():
            error(f"run_oe_source needs data\\{name}_CE.mdd: enable run_ce_source or run it first.")

    return issues


def preflight(project: Project, config: dict, check_env: bool = True) -> tuple[list[Issue], SourceScan | None]:
    """Everything that can be checked before touching any data."""
    issues = check_environment() if check_env else []

    config_issues = validate_config(config)
    issues += config_issues
    if any(i.level == "error" for i in config_issues):
        return issues, None

    scan, scan_issues = scan_sources(project)
    issues += scan_issues
    issues += check_sources(project, config, scan)
    return issues, scan
