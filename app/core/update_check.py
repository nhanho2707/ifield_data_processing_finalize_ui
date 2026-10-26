"""Check the rows of update_data.csv against the MDD before anything is written to the DDF."""
import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from object.enumerations import dataTypeConstants as T

# Category flag of the codes that cannot be combined with other codes (Don't know, None of these...).
EXCLUSIVE_FLAG = 0x1000
_CATEGORICAL_VALUE = re.compile(r"^\{(.*)\}$", re.DOTALL)
_INTEGER = re.compile(r"^[+-]?\d+$")


@dataclass(frozen=True)
class VariableInfo:
    name: str                    # full MDD name, e.g. Q1 or BLOCK[{_1}].ADDR
    datatype: int                # dataTypeConstants value
    categories: tuple = ()       # category names, in MDD order
    exclusive: frozenset = frozenset()  # lower-case names of the exclusive categories
    min_value: float | None = None  # answers (categorical), value (numeric) or length (text)
    max_value: float | None = None


@dataclass
class UpdateIssue:
    level: str  # "error" | "warning"
    instance_id: object
    question: str
    value: object
    message: str

    def __str__(self):
        return f"InstanceID {self.instance_id}, {self.question}: {self.message}"


def normalize_name(name) -> str:
    """Lookup key of a variable name: case-insensitive, X[_1].Y written like the MDD's X[{_1}].Y."""
    name = re.sub(r"\s+", "", str(name)).lower()
    return re.sub(r"\[(?!\{)([^\]]+)\]", r"[{\1}]", name)


def read_mdd_variables(mdd_file: Path) -> dict[str, VariableInfo]:
    """Every variable of an MDD (read-only), keyed by normalize_name()."""
    import win32com.client as w32

    def number(value):
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    mdm = w32.Dispatch("MDM.Document")
    mdm.Open(str(mdd_file), "", 1)  # oREAD
    try:
        variables = {}
        for variable in mdm.Variables:
            categories, exclusive = [], set()
            if variable.DataType == T.mtCategorical.value:
                for category in variable.Categories:
                    categories.append(category.Name)
                    if category.Flag & EXCLUSIVE_FLAG:
                        exclusive.add(category.Name.lower())
            variables[normalize_name(variable.FullName)] = VariableInfo(
                variable.FullName, variable.DataType, tuple(categories), frozenset(exclusive),
                number(variable.MinValue), number(variable.MaxValue))
        return variables
    finally:
        mdm.Close()


def instance_key(value) -> str:
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value).strip()


def _value(value):
    """Current Value as text, None when empty (the update clears the question)."""
    if value is None or (not isinstance(value, str) and pd.isnull(value)):
        return None
    text = str(value).strip()
    return text if text else None


def categorical_codes(value: str) -> list[str] | None:
    """Codes of a categorical value written {_1} or {_1,_2}; None when not written that way."""
    match = _CATEGORICAL_VALUE.match(value.strip())
    if match is None:
        return None
    return [code.strip() for code in match.group(1).split(",") if code.strip()]


def _format_range(variable: VariableInfo) -> str:
    low = "" if variable.min_value is None else f"{variable.min_value:g}"
    high = "" if variable.max_value is None else f"{variable.max_value:g}"
    return f"{low}..{high}"


def _check_categorical(value: str, variable: VariableInfo) -> list[tuple[str, str]]:
    codes = categorical_codes(value)
    if codes is None:
        return [("error", f"value {value} must be written as {{_1}} or {{_1,_2}}")]

    problems = []
    known = {c.lower() for c in variable.categories}
    unknown = [c for c in codes if c.lower() not in known]
    if unknown:
        listed = ", ".join(variable.categories[:30]) + (", ..." if len(variable.categories) > 30 else "")
        problems.append(("error", f"code {', '.join(unknown)} not in the MDD categories ({listed})"))

    lowered = [c.lower() for c in codes]
    repeated = sorted({c for c in codes if lowered.count(c.lower()) > 1})
    if repeated:
        problems.append(("error", f"code {', '.join(repeated)} written more than once"))

    count = len(set(lowered))
    if variable.max_value is not None and count > variable.max_value:
        if variable.max_value == 1:
            problems.append(("error", f"single-answer question: {count} codes given, only one allowed"))
        else:
            problems.append(("error", f"{count} codes given, at most {variable.max_value:g} allowed"))
    if variable.min_value is not None and 0 < count < variable.min_value:
        problems.append(("error", f"{count} codes given, at least {variable.min_value:g} required"))

    exclusive = [c for c in codes if c.lower() in variable.exclusive]
    if exclusive and count > 1:
        problems.append(("error", f"code {', '.join(exclusive)} is exclusive and cannot be combined with other codes"))
    return problems


def _check_number(value: str, variable: VariableInfo, integer: bool) -> list[tuple[str, str]]:
    if integer and not _INTEGER.match(value):
        return [("error", f"value {value} is not a whole number")]
    try:
        number = float(value)
    except ValueError:
        return [("error", f"value {value} is not a number")]
    if (variable.min_value is not None and number < variable.min_value) or \
            (variable.max_value is not None and number > variable.max_value):
        return [("error", f"value {value} outside the MDD range {_format_range(variable)}")]
    return []


def check_value(value: str, variable: VariableInfo) -> list[tuple[str, str]]:
    """(level, message) problems of a non-empty Current Value for the given variable."""
    datatype = variable.datatype
    if datatype == T.mtCategorical.value:
        return _check_categorical(value, variable)
    if datatype == T.mtLong.value:
        return _check_number(value, variable, integer=True)
    if datatype == T.mtDouble.value:
        return _check_number(value, variable, integer=False)
    if datatype == T.mtDate.value:
        try:
            pd.to_datetime(value)
        except (ValueError, OverflowError):
            return [("error", f"value {value} is not a date")]
        return []
    if datatype == T.mtBoolean.value:
        if value.lower() not in ("true", "false", "1", "0"):
            return [("error", f"value {value} is not a boolean (true/false)")]
        return []
    if datatype == T.mtText.value:
        if variable.max_value is not None and len(value) > variable.max_value:
            return [("warning", f"text of {len(value)} characters, the MDD allows {variable.max_value:g}")]
        return []
    kind = next((member.name for member in T if member.value == datatype), datatype)
    return [("error", f"{variable.name} is not a question that holds a value (data type {kind})")]


def check_update_rows(df_update_data: pd.DataFrame, variables: dict[str, VariableInfo],
                      valid_ids: set[str] | None = None, skipped_ids: dict[str, str] | None = None) -> list[UpdateIssue]:
    """Problems of every row of update_data.csv.

    valid_ids None skips the InstanceID check; skipped_ids explains why an ID of the sources is not in the data.
    """
    issues = []
    for _, row in df_update_data.iterrows():
        question, raw = row["Question Name"], row["Current Value"]
        # A column with an empty cell is read as float: show 1234, not 1234.0.
        instance_id = "" if _value(row["InstanceID"]) is None else instance_key(row["InstanceID"])

        def add(level, message):
            issues.append(UpdateIssue(level, instance_id, "" if pd.isnull(question) else str(question),
                                      _value(raw), message))

        if not instance_id:
            add("error", "InstanceID is empty")
        elif valid_ids is not None and instance_id not in valid_ids:
            reason = (skipped_ids or {}).get(instance_id)
            add("error", f"InstanceID {instance_id} is not in the data" + (f" ({reason})" if reason else ""))

        if _value(question) is None:
            add("error", "Question Name is empty")
            continue
        variable = variables.get(normalize_name(question))
        if variable is None:
            add("error", f"question {question} does not exist in the MDD")
            continue

        value = _value(raw)
        if value is not None:
            for level, message in check_value(value, variable):
                add(level, message)
    return issues


def update_literal(value, variable: VariableInfo) -> str:
    """SQL literal of a checked Current Value, written for the data type of the variable."""
    value = _value(value)
    if value is None:
        return "NULL"
    datatype = variable.datatype
    if datatype == T.mtCategorical.value:
        return "{%s}" % ",".join(categorical_codes(value))
    if datatype in (T.mtLong.value, T.mtDouble.value):
        return value
    if datatype == T.mtBoolean.value:
        return "true" if value.lower() in ("true", "1") else "false"
    return "'%s'" % value.replace("'", "''")


def write_report(issues: list[UpdateIssue], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([{"InstanceID": int(i.instance_id) if str(i.instance_id).isdigit() else i.instance_id, "Question Name": i.question, "Current Value": i.value,
                        "Level": i.level, "Problem": i.message} for i in issues])
    with pd.ExcelWriter(path, engine="xlsxwriter") as writer:
        df.to_excel(writer, sheet_name="update_data_check", index=False)
        sheet = writer.sheets["update_data_check"]
        for col, width in enumerate((14, 30, 20, 9, 90)):
            sheet.set_column(col, col, width)
        sheet.autofilter(0, 0, len(df), len(df.columns) - 1)
    return path
