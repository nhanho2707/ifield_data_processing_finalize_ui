"""iField CSV/XML -> Data Collection MDD/DDF processing (formerly ifield_processing.py)."""
import re
import shutil
import time
import traceback
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable

import pandas as pd
import win32com.client as w32

from app.core import paths
from app.core.config_model import Issue, has_errors, xml_mappings
from app.core.env_check import com_initialized
from app.core.errors import Cancelled, ConfigError, ProcessingError, SourceError
from app.core.preflight import SourceScan, preflight
from app.core.project import Project
from app.core.reporter import ConsoleReporter, Reporter
from app.core.sql_builder import build_assignments, latest_updates, update_data_statements, update_statement
from app.core.update_check import UpdateIssue, check_update_rows, instance_key, read_mdd_variables, write_report
from object.iSurvey import iSurvey
from object.metadata import Metadata


class FollowUpGlobalization(dict):
    """Translations of the follow-up stages, in the shape Metadata.translate() expects (a dict with .languages)."""

    def __init__(self):
        super().__init__()
        self.languages = []

    def add(self, globalization):
        for key, translate in globalization.items():
            # Fields under the Phase loop are looked up as "Phase[].<name>"; defined lists (MDM types)
            # and loop categories are looked up by their bare name.
            self[f"Phase[].{key}"] = translate
            self[key] = translate
        for language in globalization.languages:
            if language not in self.languages:
                self.languages.append(language)


@dataclass
class PipelineContext:
    project: Project
    config: dict
    reporter: Reporter
    scan: SourceScan
    # proto_id -> {"csv_files": [Path, ...], "survey": iSurvey | None}
    isurveys: dict = field(default_factory=dict)
    # question key -> {"question": ..., "stages": [stage_id, ...]}
    follow_up_questions: dict = field(default_factory=dict)
    follow_up_globalization: FollowUpGlobalization = field(default_factory=FollowUpGlobalization)
    shell_chain_ids: list = field(default_factory=list)
    df_respondents: pd.DataFrame = field(default_factory=pd.DataFrame)
    # InstanceID key -> _LoaiPhieu of the CSV, for the respondents of df_respondents
    respondent_loai_phieu: dict = field(default_factory=dict)
    df_update_data: pd.DataFrame = field(default_factory=pd.DataFrame)
    # MDD variables of update_data.csv, read by check_update_data (normalized name -> VariableInfo)
    update_variables: dict = field(default_factory=dict)

    @property
    def main_protoid_final(self) -> int:
        return int(self.config["main"]["protoid_final"])

    def data_file(self, suffix: str, ext: str) -> str:
        # Relative to the project folder: the DMS directives are built as ".\<path>".
        return "data\\{}{}.{}".format(self.config["project_name"], suffix, ext)

    def require_data_files(self, suffix: str):
        for ext in ("mdd", "ddf"):
            if not (self.project.root / self.data_file(suffix, ext)).is_file():
                raise ProcessingError(f"{self.data_file(suffix, ext)} does not exist (see the DMS messages above).")

    def survey_for(self, proto_id):
        entry = self.isurveys.get(int(proto_id))
        if entry is None or entry["survey"] is None:
            raise ConfigError(f"ProtoID {proto_id} should be declared in the config file.")
        if entry["survey"]["questions"] is None:
            raise ProcessingError(f"The XML of ProtoID {proto_id} has no questions.")
        return entry["survey"]


@dataclass(frozen=True)
class Step:
    key: str
    title: str
    run: Callable[[PipelineContext], None]
    # Decided by config.json alone (known before running, shown by the GUI) ...
    enabled_by_config: Callable[[dict], bool] = lambda config: True
    # ... and by what the previous steps found in the data.
    has_work: Callable[[PipelineContext], bool] = lambda ctx: True

    def should_run(self, ctx: PipelineContext) -> bool:
        return bool(self.enabled_by_config(ctx.config)) and bool(self.has_work(ctx))


@dataclass
class StepResult:
    key: str
    title: str
    status: str  # done | skipped | failed | cancelled
    elapsed: float = 0.0
    error: str | None = None


def _connection_string(ddf_file: str, mdd_file: str) -> str:
    return ("Provider=mrOleDB.Provider.2; Data Source = mrDataFileDsc; Location={}; Initial Catalog={}; "
            "Mode=ReadWrite; MR Init Category Names=1").format(ddf_file, mdd_file)


@contextmanager
def _ado_connection(connection_string: str):
    conn = w32.Dispatch("ADODB.Connection")
    conn.Open(connection_string)
    try:
        yield conn
    finally:
        conn.Close()


def _com_error_text(error) -> str:
    excepinfo = getattr(error, "excepinfo", None)
    return str(excepinfo[2]) if excepinfo and excepinfo[2] else str(error)


def _filter_dummy(df: pd.DataFrame, dummy_data_required: bool) -> pd.DataFrame:
    # dummy_data_required = true keeps ONLY the test interviews (_DefaultSP), false drops them.
    if dummy_data_required:
        return df.loc[df["System_LocationID"] == "_DefaultSP"]
    return df.loc[df["System_LocationID"] != "_DefaultSP"]


def _category_codes(value) -> set:
    # "{_1,_3}", "_3", "3", 3, 3.0 -> {"1", "3"} / {"3"}
    if pd.isna(value):
        return set()
    codes = set()
    for part in str(value).strip().strip("{}").split(","):
        part = part.strip().lstrip("_")
        try:
            part = str(int(float(part)))
        except ValueError:
            pass
        if part:
            codes.add(part)
    return codes


def _parent_names(question) -> list:
    return [q["attributes"]["objectName"] for q in question["parents"]] if "parents" in question else []


def _load_survey(project: Project, xml_file: str):
    path = project.xml_dir / xml_file
    if not path.is_file():
        raise SourceError(f"XML file not found: source\\xml\\{xml_file}")
    try:
        return iSurvey(str(path))
    except Exception as ex:
        raise SourceError(f"{xml_file}: {ex}") from ex


def read_update_data(project: Project) -> pd.DataFrame:
    # Values as text: an all-numeric column would otherwise drop leading zeros ("0912..." -> 912...).
    return pd.read_csv(project.update_data_csv, encoding="utf-8", dtype={"Previous Value": str, "Current Value": str})


def _expected_instance_ids(config: dict, scan: SourceScan) -> tuple[set[str], dict[str, str]]:
    """InstanceIDs the main section inserts from the CSV files, and why the other IDs of those files are not.

    Test interviews are filtered as insert_main does.
    """
    dummy_data_required = config["source_initialization"]["dummy_data_required"]
    reason = ("not a test interview, dummy_data_required = true" if dummy_data_required
              else "test interview (_DefaultSP), dummy_data_required = false")
    files = {f for proto_id, _ in xml_mappings(config["main"]) for f in scan.proto_files.get(int(proto_id), [])}
    ids, skipped = set(), {}
    for csv_file in files:
        df = pd.read_csv(csv_file, encoding="utf-8", low_memory=False,
                         usecols=lambda column: column in ("InstanceID", "System_LocationID"))
        if "System_LocationID" in df.columns:
            kept = _filter_dummy(df, dummy_data_required)
            skipped.update((instance_key(i), reason) for i in df["InstanceID"].drop(kept.index))
            df = kept
        ids.update(instance_key(i) for i in df["InstanceID"])
    return ids, skipped


def _ddf_instance_ids(ddf_file: str, mdd_file: str) -> set[str]:
    with _ado_connection(_connection_string(ddf_file, mdd_file)) as conn:
        records, _ = conn.Execute("SELECT InstanceID FROM VDATA")
        try:
            return set() if records.EOF else {instance_key(i) for i in records.GetRows()[0]}
        finally:
            records.Close()


def _save_update_report(project: Project, issues: list[UpdateIssue]):
    path = project.logs_dir / f"update_data_check_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return write_report(issues, path)


def check_update_file(project: Project, config: dict, scan: SourceScan) -> list[Issue]:
    """update_data.csv against the existing _EXPORT MDD, for the Check button (the run checks again)."""
    try:
        df_update_data = latest_updates(read_update_data(project))
    except Exception as ex:
        return [Issue("error", f"update_data.csv cannot be read ({ex}).")]
    if df_update_data.empty:
        return []

    name = config["project_name"]
    mdd, ddf = project.data_dir / f"{name}_EXPORT.mdd", project.data_dir / f"{name}_EXPORT.ddf"
    if not mdd.is_file():
        return [Issue("warning", f"update_data.csv is checked when running: data\\{mdd.name} does not exist yet.")]

    with com_initialized():
        variables = read_mdd_variables(mdd)
        valid_ids, skipped_ids = _expected_instance_ids(config, scan)
        keeps_data = not config["source_initialization"]["delete_all"] and not config["run_mdd_source"]
        if keeps_data and ddf.is_file():
            valid_ids |= _ddf_instance_ids(str(ddf), str(mdd))

    issues = check_update_rows(df_update_data, variables, valid_ids, skipped_ids)
    if not issues:
        return []
    report = _save_update_report(project, issues)
    errors = sum(i.level == "error" for i in issues)
    rebuilt = " (checked against the current MDD; run_mdd_source rebuilds it from XML)" if config["run_mdd_source"] else ""
    result = [Issue(i.level, f"update_data.csv: {i}") for i in issues[:100]]
    result.append(Issue("error" if errors else "warning",
                        f"update_data.csv: {errors} errors, {len(issues) - errors} warnings{rebuilt}. "
                        f"Report: logs\\{report.name}"))
    return result


# --- Steps ------------------------------------------------------------------------


def load_sources(ctx: PipelineContext):
    config, rep = ctx.config, ctx.reporter

    ctx.isurveys = {pid: {"csv_files": list(files), "survey": None} for pid, files in ctx.scan.proto_files.items()}

    for proto_id, xml_file in rep.progress(xml_mappings(config["main"]), "Read the XML files of the main section"):
        ctx.isurveys[int(proto_id)]["survey"] = _load_survey(ctx.project, xml_file)

    for stage_id, stage in rep.progress(list(config["stages"].items()), "Read the XML files of the follow-up stages"):
        mappings = xml_mappings(stage)
        for proto_id, xml_file in mappings:
            ctx.isurveys[int(proto_id)]["survey"] = _load_survey(ctx.project, xml_file)

        final_id = str(stage.get("protoid_final"))
        if final_id not in [pid for pid, _ in mappings]:
            continue

        survey = ctx.isurveys[int(final_id)]["survey"]
        for key, question in survey["questions"].items():
            entry = ctx.follow_up_questions.setdefault(key, {"stages": [], "question": question})
            entry["stages"].append(stage_id)

        ctx.follow_up_globalization.add(survey["globalization"])

    df_update_data = read_update_data(ctx.project)
    # A question updated on several rows for one InstanceID: only the last (lowest) row counts.
    ctx.df_update_data = latest_updates(df_update_data)

    rep.info(f"{len(ctx.scan.csv_files)} CSV files, {len(ctx.follow_up_questions)} follow-up questions, "
             f"{len(ctx.df_update_data)} rows in update_data.csv")
    superseded = len(df_update_data) - len(ctx.df_update_data)
    if superseded:
        rep.info(f"update_data.csv: {superseded} rows superseded by a later row of the same InstanceID and question")


def build_mdd(ctx: PipelineContext):
    config, rep, project = ctx.config, ctx.reporter, ctx.project
    base_mdd = ctx.data_file("", "mdd")
    dms_file = str(paths.output_ddf_dms())
    language = config["source_initialization"]["default_language"]

    if not config["run_mdd_source"]:
        # run_mdd_export_source: only regenerate the _EXPORT files from the existing base MDD.
        project.remove_data_files(["*_EXPORT.mdd", "*_EXPORT.ddf", "*_EXPORT.ivs", "*_CE.mdd", "*_CE.ddf", "*_CE.ivs",
                                   "*_OE.mdd", "*_OE.ddf", "*_OE.ivs", "*.xlsx"])
        Metadata(mdd_file=base_mdd, dms_file=dms_file, default_language=language).runDMS()
        ctx.require_data_files("_EXPORT")
        return

    project.data_dir.mkdir(exist_ok=True)
    project.remove_data_files(["*.mdd", "*.ddf", "*.ivs", "*.xlsx"])
    shutil.copy(paths.template_mdd(), project.root / base_mdd)

    mdd = Metadata(mdd_file=base_mdd, dms_file=dms_file, default_language=language)
    mdd.addScript("InstanceID", 'InstanceID "InstanceID" text;')

    main_survey = ctx.isurveys[ctx.main_protoid_final]["survey"]
    globalization = main_survey["globalization"]

    for question in rep.progress(list(main_survey["questions"].values()), "Add the main questions to the MDD"):
        name = question["attributes"]["objectName"]
        parents = _parent_names(question)

        if "syntax" in question:
            mdd.addScript(name, question["syntax"], is_defined_list=question["is_defined_list"],
                          parent_nodes=parents, globalization=globalization)
            if "comment_syntax" in question:
                mdd.addScript(f'{name}{question["comment"]["objectName"]}', question["comment_syntax"],
                              parent_nodes=parents, globalization=globalization)
        elif "comment_syntax" in question:
            mdd.addScript(name, question["comment_syntax"], is_defined_list=question["is_defined_list"],
                          parent_nodes=parents, globalization=globalization)

    if ctx.follow_up_questions:
        stages = ",".join('{} "{}"'.format(stage.replace("-", "_"), stage) for stage in config["stages"].keys())
        mdd.addScript("Phase", 'Phase "" loop {%s} fields ()expand grid;' % stages)
        mdd.addScript("InstanceID", 'InstanceID "InstanceID" text;', parent_nodes=["Phase"])

        for entry in rep.progress(list(ctx.follow_up_questions.values()), "Add the follow-up questions to the MDD"):
            question = entry["question"]
            if "syntax" not in question:
                continue

            name = question["attributes"]["objectName"]
            parent_nodes = [] if question["is_defined_list"] else ["Phase"]
            parent_nodes.extend(_parent_names(question))

            mdd.addScript(name, question["syntax"], is_defined_list=question["is_defined_list"],
                          parent_nodes=parent_nodes, globalization=ctx.follow_up_globalization)
            if "comment_syntax" in question:
                mdd.addScript(f'{name}{question["comment"]["objectName"]}', question["comment_syntax"],
                              parent_nodes=parent_nodes, globalization=ctx.follow_up_globalization)

    rep.info("Running OutputDDFFile.dms")
    mdd.runDMS()
    ctx.require_data_files("_EXPORT")


def check_update_data(ctx: PipelineContext):
    """Every row of update_data.csv against the _EXPORT MDD, before any data is inserted or updated."""
    rep, config = ctx.reporter, ctx.config
    mdd_file, ddf_file = ctx.data_file("_EXPORT", "mdd"), ctx.data_file("_EXPORT", "ddf")
    ctx.require_data_files("_EXPORT")

    ctx.update_variables = read_mdd_variables(ctx.project.root / mdd_file)
    valid_ids, skipped_ids = _expected_instance_ids(config, ctx.scan)
    if not config["source_initialization"]["delete_all"]:
        valid_ids |= _ddf_instance_ids(ddf_file, mdd_file)

    issues = check_update_rows(ctx.df_update_data, ctx.update_variables, valid_ids, skipped_ids)
    errors = [i for i in issues if i.level == "error"]
    cleared = int(ctx.df_update_data["Current Value"].isna().sum())
    if not issues:
        rep.info(f"update_data.csv: {len(ctx.df_update_data)} rows match the MDD"
                 + (f" ({cleared} empty values clear their question)" if cleared else ""))
        return

    report = _save_update_report(ctx.project, issues)
    for issue in issues[:100]:
        rep.log(f"update_data.csv: {issue}", issue.level)
    if len(issues) > 100:
        rep.log(f"... {len(issues) - 100} more in the report", "error" if errors else "warning")
    rep.info(f"Report: {report}")
    if errors:
        raise ProcessingError(f"update_data.csv has {len(errors)} errors: no data was inserted or updated. "
                              f"Fix the file (see logs\\{report.name}) and run again.")


def insert_main_data(ctx: PipelineContext):
    config, rep = ctx.config, ctx.reporter
    mdd_file, ddf_file = ctx.data_file("_EXPORT", "mdd"), ctx.data_file("_EXPORT", "ddf")
    ctx.require_data_files("_EXPORT")
    connection_string = _connection_string(ddf_file, mdd_file)

    init = config["source_initialization"]
    removed_columns = set(config["respondent_information_columns_removed"])
    respondent_columns = list(config["respondent_information_columns"].values())

    if init["delete_all"]:
        rep.info("delete_all = true: deleting all existing records")
        with _ado_connection(connection_string) as conn:
            conn.Execute("DELETE FROM VDATA")

    for proto_id, _ in xml_mappings(config["main"]):
        for csv_file in ctx.isurveys[int(proto_id)]["csv_files"]:
            df = pd.read_csv(csv_file, encoding="utf-8", low_memory=False)
            df.set_index(["InstanceID"], inplace=True)
            df = _filter_dummy(df, init["dummy_data_required"])

            existing = Metadata(mdd_file=mdd_file, ddf_file=ddf_file, sql_query="SELECT InstanceID, SHELL_CHAINID FROM VDATA") \
                .convertToDataFrame(questions=["InstanceID", "SHELL_CHAINID"])
            if not existing.empty:
                existing.set_index(["InstanceID"], inplace=True)
                ctx.shell_chain_ids = list(existing["SHELL_CHAINID"])
            existing_ids = set(existing.index)

            ids = [i for i in df.index if str(i) not in existing_ids]
            rep.info(f"{csv_file.name}: {len(ids)} new InstanceIDs (ProtoID {proto_id})")
            if not ids:
                continue

            df_data = df.loc[ids]
            ctx.df_respondents = pd.concat([ctx.df_respondents, df_data[respondent_columns]], axis=0, ignore_index=False)
            if "_LoaiPhieu" in df_data.columns:
                ctx.respondent_loai_phieu.update(zip(map(_instance_key, df_data.index), df_data["_LoaiPhieu"]))

            # Rows as plain dicts: much faster to read cell by cell than the Series of iterrows().
            rows = zip(df_data.index, df_data.to_dict("records"))
            with _ado_connection(connection_string) as conn:
                for instance_id, row in rep.progress(rows, f"Insert {len(ids)} InstanceIDs", total=len(df_data)):
                    survey = ctx.survey_for(row["ProtoSurveyID"])
                    try:
                        conn.Execute("INSERT INTO VDATA(InstanceID) VALUES(%s)" % instance_id)
                        assignments = build_assignments(row, survey, removed_columns=removed_columns)
                        if assignments:
                            conn.Execute(update_statement(assignments, "InstanceID = {}".format(instance_id)))
                        ctx.shell_chain_ids.append(row["SHELL_CHAINID"])
                    except Exception as error:
                        raise ProcessingError(f"InstanceID {instance_id}: {_com_error_text(error)}\n{traceback.format_exc()}") from error


def mdd_to_csv_columns(isurveys: dict) -> dict:
    """MDD variable name -> CSV column name, from the column maps of every loaded survey."""
    aliases = {}
    for entry in isurveys.values():
        survey = entry["survey"]
        if survey is None or survey["questions"] is None:
            continue
        for question in survey["questions"].values():
            for column_map in question.get("columns", []):
                for mdd_col, csv_obj in column_map.items():
                    if csv_obj["csv"]:
                        aliases.setdefault(mdd_col, csv_obj["csv"][0])
                    for other_col, other_obj in csv_obj.get("others", {}).items():
                        if other_obj["csv"]:
                            aliases.setdefault(other_col, other_obj["csv"][0])
    return aliases


def _instance_key(value) -> str:
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def apply_updates_to_respondents(df_respondents: pd.DataFrame, df_update_data: pd.DataFrame, aliases: dict) -> dict:
    """Apply the update_data.csv rows that target a column of the RESPONDENT sheet (in place).

    update_data.csv names MDD variables ("Question Name"); the sheet has the CSV column names.
    Returns counters: applied, other_questions (not respondent columns), unknown_ids.
    """
    stats = {"applied": 0, "other_questions": 0, "unknown_ids": set()}
    if df_respondents.empty or df_update_data.empty:
        return stats

    columns = list(df_respondents.columns)
    by_lower = {str(c).lower(): c for c in columns}
    rows_by_id = {}
    for label in df_respondents.index:
        rows_by_id.setdefault(_instance_key(label), label)

    def column_for(question):
        bracketed = re.sub(r"\}\]", "]", re.sub(r"\[\{", "[", question))  # X[{_1}].Y -> X[_1].Y
        for candidate in (question, aliases.get(question), bracketed):
            if candidate in columns:
                return candidate
            if candidate is not None and candidate.lower() in by_lower:
                return by_lower[candidate.lower()]
        return None

    for _, row in df_update_data.iterrows():
        column = column_for(str(row["Question Name"]))
        if column is None:
            stats["other_questions"] += 1
            continue
        label = rows_by_id.get(_instance_key(row["InstanceID"]))
        if label is None:
            stats["unknown_ids"].add(row["InstanceID"])
            continue
        if df_respondents[column].dtype != object:
            df_respondents[column] = df_respondents[column].astype(object)
        df_respondents.loc[label, column] = row["Current Value"]
        stats["applied"] += 1

    return stats


def cancelled_respondents(df_respondents: pd.DataFrame, loai_phieu: dict, df_update_data: pd.DataFrame) -> list:
    """Index labels of the respondents whose final _LoaiPhieu is {_3} (cancelled).

    The CSV value (loai_phieu: InstanceID key -> value) is overridden by the _LoaiPhieu rows of update_data.csv.
    """
    final = dict(loai_phieu)
    if not df_update_data.empty:
        rows = df_update_data[df_update_data["Question Name"].astype(str).str.strip().str.lower() == "_loaiphieu"]
        final.update(zip(map(_instance_key, rows["InstanceID"]), rows["Current Value"]))
    return [label for label in df_respondents.index.unique() if "3" in _category_codes(final.get(_instance_key(label)))]


def export_respondents(ctx: PipelineContext):
    df_respondents = ctx.df_respondents

    # Personal information corrected through update_data.csv (the DDF gets the same rows in apply_update_data).
    stats = apply_updates_to_respondents(df_respondents, ctx.df_update_data, mdd_to_csv_columns(ctx.isurveys))
    if not ctx.df_update_data.empty:
        ctx.reporter.info(f"update_data.csv: {stats['applied']} values applied to the RESPONDENT sheet, "
                          f"{stats['other_questions']} rows are other questions (DDF only)")
    if stats["unknown_ids"]:
        ctx.reporter.warning(f"update_data.csv: {len(stats['unknown_ids'])} InstanceIDs are not among the respondents "
                             f"inserted in this run: {', '.join(map(str, sorted(stats['unknown_ids'], key=str)[:20]))}")

    # Cancelled interviews stay in the DDF (remove_ids deletes them there) but not in the RESPONDENT sheet.
    cancelled = cancelled_respondents(df_respondents, ctx.respondent_loai_phieu, ctx.df_update_data)
    if cancelled:
        df_respondents = df_respondents.drop(index=cancelled)
        ctx.reporter.info(f"{len(cancelled)} cancelled InstanceIDs (_LoaiPhieu {{_3}}) left out of the RESPONDENT sheet")

    respondent_file = ctx.project.root / ctx.data_file("_RESPONDENT", "xlsx")
    with pd.ExcelWriter(respondent_file, engine="xlsxwriter", mode="w") as writer:
        df_respondents.to_excel(writer, sheet_name="RESPONDENT")
    ctx.reporter.info(f"Saved {respondent_file.name} ({len(df_respondents)} respondents)")


def insert_stage_data(ctx: PipelineContext):
    config, rep = ctx.config, ctx.reporter
    connection_string = _connection_string(ctx.data_file("_EXPORT", "ddf"), ctx.data_file("_EXPORT", "mdd"))
    dummy_data_required = config["source_initialization"]["dummy_data_required"]
    removed_columns = set(config["respondent_information_columns_removed"])

    for stage_id, stage in config["stages"].items():
        prefix = "Phase[{%s}]." % stage_id.replace("-", "_")

        for proto_id, _ in xml_mappings(stage):
            entry = ctx.isurveys.get(int(proto_id))
            if entry is None:
                continue

            for csv_file in entry["csv_files"]:
                df = pd.read_csv(csv_file, encoding="utf-8", low_memory=False)
                df.set_index(["SHELL_CHAINID"], inplace=True)
                df = _filter_dummy(df, dummy_data_required)

                known = set(ctx.shell_chain_ids)
                recall_ids = [i for i in df.index if i in known or str(i) in known]
                rep.info(f"{stage_id} / {csv_file.name}: {len(recall_ids)} matching SHELL_CHAINIDs (ProtoID {proto_id})")
                if not recall_ids:
                    continue

                df_data = df.loc[recall_ids]

                rows = zip(df_data.index, df_data.to_dict("records"))
                with _ado_connection(connection_string) as conn:
                    for chain_id, row in rep.progress(rows, f"Insert {len(recall_ids)} rows into {stage_id}", total=len(df_data)):
                        survey = ctx.survey_for(row["ProtoSurveyID"])
                        try:
                            assignments = [(f"{prefix}InstanceId", str(row["InstanceID"]))]
                            assignments += build_assignments(row, survey, prefix=prefix, removed_columns=removed_columns,
                                                             skip_questions={"SHELL_CHAINID"},
                                                             check_answer_set=False, quote_object_text=False)
                            conn.Execute(update_statement(assignments, "SHELL_CHAINID = '{}'".format(chain_id)))
                        except Exception as error:
                            raise ProcessingError(f"{stage_id} SHELL_CHAINID {chain_id}: {_com_error_text(error)}\n{traceback.format_exc()}") from error


def apply_update_data(ctx: PipelineContext):
    rep = ctx.reporter
    statements = update_data_statements(ctx.df_update_data, ctx.update_variables)
    connection_string = _connection_string(ctx.data_file("_EXPORT", "ddf"), ctx.data_file("_EXPORT", "mdd"))

    failed = 0
    with _ado_connection(connection_string) as conn:
        for instance_id, sql in rep.progress(statements, "Apply update_data.csv"):
            try:
                conn.Execute(sql)
            except Exception as error:
                failed += 1
                rep.error(f"update_data.csv, InstanceID {instance_id}: {_com_error_text(error)}\n{sql}")

    if failed:
        raise ProcessingError(f"{failed}/{len(statements)} respondents of update_data.csv were not updated (see above).")
    rep.info(f"update_data.csv: {len(statements)} respondents updated")


def remove_invalid_ids(ctx: PipelineContext):
    connection_string = _connection_string(ctx.data_file("_EXPORT", "ddf"), ctx.data_file("_EXPORT", "mdd"))
    try:
        with _ado_connection(connection_string) as conn:
            conn.Execute("DELETE FROM VDATA WHERE Not _LoaiPhieu.ContainsAny({_1,_2,_5})")
    except Exception as error:
        # Not every questionnaire has _LoaiPhieu; the original script ignored this silently.
        ctx.reporter.warning(f"Could not remove cancelled/extra IDs: {_com_error_text(error)}")


def run_clean_ce(ctx: PipelineContext):
    ctx.project.remove_data_files(["*_CE.mdd", "*_CE.ddf", "*_CE.ivs", "*_OE.mdd", "*_OE.ddf", "*_OE.ivs"])
    ctx.require_data_files("_EXPORT")

    mdd = Metadata(mdd_file=ctx.data_file("_EXPORT", "mdd"), ddf_file=ctx.data_file("_EXPORT", "ddf"),
                   dms_file="dms\\CLEAN_DATA_SCRIPT.dms",
                   default_language=ctx.config["source_initialization"]["default_language"], sql_query="SELECT * FROM VDATA")
    mdd.addAxisExpressions(axisexpressions=ctx.config["axis_expression"])
    mdd.runCleanDataDMS(mode="CE")
    ctx.require_data_files("_CE")


def run_clean_oe(ctx: PipelineContext):
    ctx.project.remove_data_files(["*_OE.mdd", "*_OE.ddf", "*_OE.ivs"])
    ctx.require_data_files("_CE")

    mdd = Metadata(mdd_file=ctx.data_file("_CE", "mdd"), ddf_file=ctx.data_file("_CE", "ddf"),
                   dms_file="dms\\CLEAN_DATA_PROCESSING.dms",
                   default_language=ctx.config["source_initialization"]["default_language"], sql_query="SELECT * FROM VDATA")
    mdd.runCleanDataDMS(mode="OE")
    ctx.require_data_files("_OE")


STEPS = [
    Step("load_sources", "Read the CSV/XML sources", load_sources),
    Step("build_mdd", "Build the MDD/DDF files", build_mdd,
         enabled_by_config=lambda config: config["run_mdd_source"] or config["run_mdd_export_source"]),
    Step("check_updates", "Check update_data.csv", check_update_data,
         has_work=lambda ctx: not ctx.df_update_data.empty),
    Step("insert_main", "Insert the main section data", insert_main_data),
    Step("export_respondents", "Export respondent information", export_respondents,
         has_work=lambda ctx: not ctx.df_respondents.empty),
    Step("insert_stages", "Insert the follow-up stage data", insert_stage_data,
         has_work=lambda ctx: bool(ctx.follow_up_questions)),
    Step("apply_updates", "Apply update_data.csv", apply_update_data,
         has_work=lambda ctx: not ctx.df_update_data.empty),
    Step("remove_ids", "Remove cancelled/extra IDs", remove_invalid_ids,
         enabled_by_config=lambda config: config["source_initialization"]["remove_all_ids"]),
    Step("clean_ce", "Clean data (CE)", run_clean_ce,
         enabled_by_config=lambda config: config["processing_data"]["run_ce_source"]),
    Step("clean_oe", "Process open ends (OE)", run_clean_oe,
         enabled_by_config=lambda config: config["processing_data"]["run_oe_source"]),
]


# Files saved by newer Data Collection versions get an mdm_lastversion older versions refuse to open.
_MDM_VERSION_PATTERN = re.compile(r'mdm_lastversion="(?!6\.\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})[^"]+"')


def fix_mdm_versions(ctx: PipelineContext):
    for suffix in ("_EXPORT", "_CE", "_OE"):
        path = ctx.project.root / ctx.data_file(suffix, "mdd")
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8")
        fixed = _MDM_VERSION_PATTERN.sub('mdm_lastversion="6.0.1.1.46"', content)
        if fixed != content:
            path.write_text(fixed, encoding="utf-8")
            ctx.reporter.info(f"Set mdm_lastversion to 6.0.1.1.46 in {path.name}")


def run_pipeline(project: Project, reporter: Reporter | None = None, config: dict | None = None) -> list[StepResult]:
    """Run every enabled step. Raises the first error after reporting it; steps after it are not run."""
    reporter = reporter or ConsoleReporter()
    config = config or project.load_config()
    results: list[StepResult] = []
    log_path = project.logs_dir / f"run_{datetime.now():%Y%m%d_%H%M%S}.log"

    with reporter.log_to_file(log_path), com_initialized(), project.working_directory(), reporter.capture_stdout():
        reporter.info(f"Project {config['project_name']} ({project.root})")
        reporter.info(f"Log file: {log_path}")

        issues, scan = preflight(project, config)
        for issue in issues:
            reporter.log(issue.message, issue.level)
        if has_errors(issues):
            raise ConfigError("Preflight check failed, nothing was processed. Fix the errors above and run again.")

        ctx = PipelineContext(project=project, config=config, reporter=reporter, scan=scan)
        try:
            for step in STEPS:
                if not step.should_run(ctx):
                    results.append(StepResult(step.key, step.title, "skipped"))
                    reporter.step(step.key, step.title, "skipped")
                    continue

                reporter.check_cancelled()
                reporter.step(step.key, step.title, "running")
                started = time.perf_counter()
                try:
                    step.run(ctx)
                except Exception as error:
                    status = "cancelled" if isinstance(error, Cancelled) else "failed"
                    elapsed = time.perf_counter() - started
                    results.append(StepResult(step.key, step.title, status, elapsed, str(error)))
                    reporter.step(step.key, step.title, status, elapsed, str(error))
                    raise

                elapsed = time.perf_counter() - started
                results.append(StepResult(step.key, step.title, "done", elapsed))
                reporter.step(step.key, step.title, "done", elapsed)
        finally:
            try:
                fix_mdm_versions(ctx)
            except Exception as error:
                reporter.warning(f"Could not fix mdm_lastversion: {error}")

    return results
