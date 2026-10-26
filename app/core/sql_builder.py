"""Pure functions turning iField CSV rows into mrOleDB SQL statements (no COM needed)."""
import re

import pandas as pd

from app.core.update_check import normalize_name, update_literal
from object.enumerations import dataTypeConstants


def sql_text(value) -> str:
    """Quoted text literal: single quotes doubled, line breaks flattened to '. '."""
    return "'{}'".format(". ".join(re.split("\n|\r", re.sub(pattern="[']", repl="''", string=str(value)))))


def sql_quoted(value) -> str:
    return "'{}'".format(value)


def sql_raw(value) -> str:
    return "{}".format(value)


def _is_categorical(question, csv_obj) -> bool:
    datatype = question["datatype"].value
    return datatype == dataTypeConstants.mtCategorical.value or (
        datatype == dataTypeConstants.mtObject.value and csv_obj["datatype"].value == dataTypeConstants.mtCategorical.value
    )


def build_assignments(row, survey, *, prefix="", removed_columns=(), skip_questions=(),
                      check_answer_set=True, quote_object_text=True) -> list[tuple[str, str]]:
    """(mdd column, SQL literal) pairs for one CSV row of the given iSurvey.

    The main section and the follow-up stages historically used slightly different rules;
    they are kept as parameters:
      prefix             -- e.g. "Phase[{stage_1}]." for follow-up stages
      removed_columns    -- CSV columns never written (respondent personal information)
      skip_questions     -- question objectNames to ignore
      check_answer_set   -- skip categorical questions whose answerSetID is "8" or "-1"
      quote_object_text  -- quote text sub-columns of object questions

    row is a dict (column -> value) or a pandas Series. Pass dicts in row loops: indexing a
    Series cell by cell is what used to make the insert steps slow on wide CSV files.
    """
    if isinstance(row, pd.Series):
        row = row.to_dict()
    assignments = []

    for question in survey["questions"].values():
        if question["attributes"]["objectName"] in skip_questions:
            continue
        if question["datatype"] in [dataTypeConstants.mtNone, dataTypeConstants.mtLevel]:
            continue

        for column_map in question["columns"]:
            for mdd_col, csv_obj in column_map.items():
                csv_cols = csv_obj["csv"]
                if len(csv_cols) == 0 or csv_cols[0] in removed_columns:
                    continue

                target = prefix + mdd_col

                if _is_categorical(question, csv_obj):
                    answer_set_id = question["answers"]["attributes"]["answerSetID"]
                    if check_answer_set and answer_set_id in ("8", "-1"):
                        continue

                    if bool(int(question["answers"]["answerref"]["attributes"]["isMultipleSelection"])):
                        values = {k: row[k] for k in csv_cols}
                        if sum(v for v in values.values() if not pd.isnull(v)) > 0:
                            selected = [k.split(".")[-1] for k, v in values.items() if v == 1]
                            assignments.append((target, "{%s}" % ",".join(selected)))
                    elif not pd.isnull(row[csv_cols[0]]):
                        option = question["answers"]["options"][str(int(row[csv_cols[0]]))]
                        assignments.append((target, "{%s}" % option["objectname"]))

                    for other_col, other_obj in csv_obj["others"].items():
                        value = row[other_obj["csv"][0]]
                        if pd.isnull(value):
                            continue
                        match int(other_obj["datatype"]):  # 2 = number, 3 = text, 4 = quoted value
                            case 2:
                                assignments.append((prefix + other_col, sql_raw(value)))
                            case 3:
                                assignments.append((prefix + other_col, sql_text(value)))
                            case 4:
                                assignments.append((prefix + other_col, sql_quoted(value)))
                else:
                    value = row[csv_cols[0]]
                    if pd.isnull(value):
                        continue
                    match question["datatype"].value:
                        case dataTypeConstants.mtText.value:
                            assignments.append((target, sql_text(value)))
                        case dataTypeConstants.mtDate.value:
                            assignments.append((target, sql_quoted(value)))
                        case dataTypeConstants.mtDouble.value:
                            assignments.append((target, sql_raw(value)))
                        case dataTypeConstants.mtObject.value:
                            if quote_object_text and csv_obj["datatype"].value == dataTypeConstants.mtText.value:
                                assignments.append((target, sql_quoted(value)))
                            else:
                                assignments.append((target, sql_raw(value)))

    return assignments


def update_statement(assignments, where: str) -> str:
    return "UPDATE VDATA SET " + ",".join(f"{column} = {value}" for column, value in assignments) + f" WHERE {where}"


def update_data_value(value) -> str:
    """Literal for a "Current Value" of update_data.csv.

    Digits are written as a number, except with a leading zero (phone numbers, codes) where the
    number would lose it; everything else is a quoted text literal.
    """
    if pd.isnull(value):
        return "NULL"
    text = str(value)
    if text.isnumeric() and not (len(text) > 1 and text.startswith("0")):
        return text
    return "'%s'" % text.replace("'", "''")


def latest_updates(df_update_data: pd.DataFrame) -> pd.DataFrame:
    """Keep only the last (most recent) row of each InstanceID + Question Name of update_data.csv.

    A question updated twice for the same respondent must end with the value of the lower row;
    question names are compared case-insensitively, as MDD variable names are.
    """
    if df_update_data.empty:
        return df_update_data
    keys = pd.DataFrame({"id": df_update_data["InstanceID"].astype(str).str.strip(),
                         "question": df_update_data["Question Name"].astype(str).str.strip().str.lower()})
    return df_update_data[~keys.duplicated(keep="last")]


def update_data_statements(df_update_data: pd.DataFrame, variables: dict | None = None) -> list[tuple[object, str]]:
    """(InstanceID, UPDATE statement) for every respondent listed in update_data.csv.

    With the MDD variables (read_mdd_variables, rows already checked), each value is written for the
    data type of its question ({_1,_2} categorical, quoted text...) under its MDD name.
    """
    df = latest_updates(df_update_data).set_index("InstanceID")
    statements = []

    def assignment(question, value):
        if variables is None:
            return "%s = %s" % (question, update_data_value(value))
        variable = variables[normalize_name(question)]
        return "%s = %s" % (variable.name, update_literal(value, variable))

    for instance_id in dict.fromkeys(df.index):
        rows = df.loc[[instance_id], ["Question Name", "Current Value"]]
        assignments = ",".join(assignment(question, value) for question, value in rows.itertuples(index=False))
        statements.append((instance_id, "UPDATE VDATA SET %s WHERE InstanceID = %s" % (assignments, instance_id)))

    return statements
