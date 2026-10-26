import copy
import json
from dataclasses import dataclass
from pathlib import Path

from app.core.errors import ConfigError

# Optional keys and the value used when a project's config.json omits them.
DEFAULTS = {
    "run_mdd_source": True,
    "run_mdd_export_source": False,
    "source_initialization": {
        "default_language": "VIT",
        "delete_all": False,
        "remove_all_ids": True,
        "dummy_data_required": False,
    },
    "processing_data": {
        "run_ce_source": False,
        "run_oe_source": False,
    },
    "stages": {},
    "respondent_information_columns": {},
    "respondent_information_columns_removed": [],
    "axis_expression": {},
}


@dataclass
class Issue:
    level: str  # "error" | "warning"
    message: str

    def __str__(self):
        return f"[{self.level.upper()}] {self.message}"


def has_errors(issues) -> bool:
    return any(issue.level == "error" for issue in issues)


def is_placeholder(value) -> bool:
    """True for the template's "--Enter a ...--" values."""
    return "Enter a" in str(value)


def xml_mappings(section: dict) -> list[tuple[str, str]]:
    """(proto_id, xml_file) pairs of a main/stage section, without template placeholders."""
    return [(str(pid), xml) for pid, xml in section.get("xmls", {}).items() if not is_placeholder(pid)]


def _with_defaults(config: dict) -> dict:
    merged = copy.deepcopy(config)
    for key, default in DEFAULTS.items():
        if key not in merged:
            merged[key] = copy.deepcopy(default)
        elif isinstance(default, dict) and default and isinstance(merged[key], dict):
            for sub_key, sub_default in default.items():
                merged[key].setdefault(sub_key, sub_default)
    return merged


def load_config(path: Path) -> dict:
    if not path.is_file():
        raise ConfigError(f"config.json not found: {path}")
    try:
        with open(path, mode="r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as ex:
        raise ConfigError(f"config.json is not valid JSON (line {ex.lineno}, column {ex.colno}): {ex.msg}") from ex
    return _with_defaults(config)


def save_config(path: Path, config: dict):
    with open(path, mode="w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=4)


def _is_int(value) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def validate_config(config: dict) -> list[Issue]:
    """Checks that only need config.json itself (no file system access)."""
    issues = []

    def error(message):
        issues.append(Issue("error", message))

    if not config.get("project_name") or is_placeholder(config["project_name"]):
        error("project_name is empty.")

    if not config.get("source_initialization", {}).get("default_language"):
        error("source_initialization.default_language is empty.")

    main = config.get("main")
    if not isinstance(main, dict):
        error('Section "main" is missing.')
        return issues

    if any(is_placeholder(pid) for pid in main.get("xmls", {})):
        error('main.xmls still contains "--Enter a protodid--" placeholder rows: fill them in or remove them.')

    main_ids = [pid for pid, _ in xml_mappings(main)]
    if not main_ids:
        error("main.xmls has no XML file.")
    for pid in main_ids:
        if not _is_int(pid):
            error(f'main.xmls: ProtoID "{pid}" is not a number.')

    final = main.get("protoid_final")
    if not _is_int(final):
        error(f'main.protoid_final "{final}" is not a number.')
    elif main_ids and str(int(final)) not in main_ids:
        error(f"main.protoid_final {final} is not listed in main.xmls.")

    for stage_id, stage in config.get("stages", {}).items():
        stage_ids = [pid for pid, _ in xml_mappings(stage)]
        for pid in stage_ids:
            if not _is_int(pid):
                error(f'stages.{stage_id}.xmls: ProtoID "{pid}" is not a number.')
        if stage_ids and str(stage.get("protoid_final")) not in stage_ids:
            error(f"stages.{stage_id}.protoid_final {stage.get('protoid_final')} is not listed in stages.{stage_id}.xmls.")

    return issues
