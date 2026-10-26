"""Tests of the core logic that does not need Data Collection.

    python -m unittest discover -s tests -t .
"""
import shutil
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

import app.core  # noqa: F401
from app.core.config_model import has_errors, load_config, save_config, validate_config, xml_mappings
from app.core.errors import ConfigError
from app.core.preflight import check_sources, scan_sources
from app.core.project import create_project, list_projects
from app.core.sql_builder import build_assignments, sql_text, update_data_statements, update_statement
from object.enumerations import dataTypeConstants as T


def _question(name, datatype, csv, multi=False, answer_set="1", others=None, col_dtype=None):
    column = {"csv": csv, "others": others or {}}
    if col_dtype is not None:
        column["datatype"] = col_dtype
    return {
        "attributes": {"objectName": name}, "datatype": datatype, "columns": [{name: column}],
        "answers": {"attributes": {"answerSetID": answer_set},
                    "answerref": {"attributes": {"isMultipleSelection": "1" if multi else "0"}},
                    "options": {"1": {"objectname": "_1"}, "2": {"objectname": "_2"}}},
    }


SURVEY = {"questions": {
    "SA": _question("SA", T.mtCategorical, ["SA"], others={"SA._97": {"csv": ["SA_other"], "datatype": "3"}}),
    "MA": _question("MA", T.mtCategorical, ["MA._1", "MA._2"], multi=True),
    "SA8": _question("SA8", T.mtCategorical, ["SA8"], answer_set="8"),
    "TXT": _question("TXT", T.mtText, ["TXT"]),
    "OBJ": _question("OBJ", T.mtObject, ["OBJ"], col_dtype=T.mtText),
    "_ResName": _question("_ResName", T.mtText, ["_ResName"]),
    "SHELL_CHAINID": _question("SHELL_CHAINID", T.mtText, ["SHELL_CHAINID"]),
}}

ROW = pd.Series({"SA": 2.0, "SA_other": "a'b\nc", "MA._1": 1, "MA._2": 1, "SA8": 1.0, "TXT": np.nan,
                 "OBJ": "x", "_ResName": "Nguyen", "SHELL_CHAINID": "CH1"}, name=1001)


class SqlBuilderTest(unittest.TestCase):
    def test_main_rules(self):
        assignments = build_assignments(ROW, SURVEY, removed_columns={"_ResName"})
        self.assertEqual(assignments, [
            ("SA", "{_2}"), ("SA._97", "'a''b. c'"), ("MA", "{_1,_2}"), ("OBJ", "'x'"), ("SHELL_CHAINID", "'CH1'"),
        ])

    def test_stage_rules(self):
        assignments = build_assignments(ROW, SURVEY, prefix="Phase[{stage_1}].", removed_columns={"_ResName"},
                                        skip_questions={"SHELL_CHAINID"}, check_answer_set=False, quote_object_text=False)
        columns = [c for c, _ in assignments]
        self.assertIn(("Phase[{stage_1}].SA8", "{_1}"), assignments)
        self.assertIn(("Phase[{stage_1}].OBJ", "x"), assignments)
        self.assertNotIn("Phase[{stage_1}]._ResName", columns)
        self.assertNotIn("Phase[{stage_1}].SHELL_CHAINID", columns)

    def test_follow_up_globalization(self):
        from app.core.pipeline import FollowUpGlobalization

        class Globalization(dict):
            def __init__(self, items, languages):
                super().__init__(items)
                self.languages = languages

        g = FollowUpGlobalization()
        g.add(Globalization({"Q1": {"vi": "Câu 1"}, "_LIST": {"vi": "Danh sách"}}, ["vi"]))
        g.add(Globalization({"Q1": {"vi": "Câu 1 (stage 2)", "en": "Q 1"}}, ["vi", "en"]))
        self.assertEqual(g.languages, ["vi", "en"])
        self.assertEqual(g["Phase[].Q1"], {"vi": "Câu 1 (stage 2)", "en": "Q 1"})
        self.assertEqual(g["_LIST"], {"vi": "Danh sách"})

    def test_update_statement(self):
        self.assertEqual(update_statement([("A", "1"), ("B", "'x'")], "InstanceID = 5"),
                         "UPDATE VDATA SET A = 1,B = 'x' WHERE InstanceID = 5")
        self.assertEqual(sql_text("it's\r\nok"), "'it''s. . ok'")

    def test_update_data_statements(self):
        df = pd.DataFrame({"InstanceID": [1, 2, 2, 3, 3, 3],
                           "Question Name": ["Q1", "Q2", "Q3", "PHONE", "NAME", "ZERO"],
                           "Current Value": ["5", "abc", np.nan, "0912345678", "O'Neil", "0"]})
        self.assertEqual(dict(update_data_statements(df)), {
            1: "UPDATE VDATA SET Q1 = 5 WHERE InstanceID = 1",
            2: "UPDATE VDATA SET Q2 = 'abc',Q3 = NULL WHERE InstanceID = 2",
            3: "UPDATE VDATA SET PHONE = '0912345678',NAME = 'O''Neil',ZERO = 0 WHERE InstanceID = 3",
        })

    def test_update_data_keeps_the_last_row_of_a_question(self):
        df = pd.DataFrame({"InstanceID": [1, 1, 2, 1, 2],
                           "Question Name": ["Q1", "Q2", "Q1", "q1", "Q1"],
                           "Current Value": ["5", "7", "1", "6", "2"]})
        self.assertEqual(dict(update_data_statements(df)), {
            1: "UPDATE VDATA SET Q2 = 7,q1 = 6 WHERE InstanceID = 1",
            2: "UPDATE VDATA SET Q1 = 2 WHERE InstanceID = 2",
        })


class RespondentUpdateTest(unittest.TestCase):
    def test_update_data_reaches_the_respondent_sheet(self):
        from app.core.pipeline import apply_updates_to_respondents, mdd_to_csv_columns

        df = pd.DataFrame({
            "_ResName": ["An", "Binh"], "_ResPhone._C_1": [909000001, 909000002],
            "_ResWardSelected": ["W1", "W1"], "BLOCK[_1].ADDR": ["a", "b"],
        }, index=pd.Index([1001, 1002], name="InstanceID"))
        updates = pd.DataFrame([
            (1001, "_ResName", "", "An Nguyen"),
            (1001, "_ResWardSelected", "W1", "W2"),           # not in respondent_information_columns_removed
            (1002, "_ResPhone_C_1", "", "0912345678"),       # MDD name differs from the CSV column
            (1002, "BLOCK[{_1}].ADDR", "b", "new address"),  # MDD [{...}] vs CSV [...]
            (1002, "_resname", "Binh", np.nan),               # case-insensitive, cleared value
            (1001, "Q5", 1, 2),                               # ordinary question: DDF only
            (9999, "_ResName", "", "Ghost"),                  # not inserted in this run
        ], columns=["InstanceID", "Question Name", "Previous Value", "Current Value"])
        isurveys = {1: {"survey": {"questions": {"_ResPhone": {"columns": [
            {"_ResPhone_C_1": {"csv": ["_ResPhone._C_1"], "others": {}}}]}}}}}

        stats = apply_updates_to_respondents(df, updates, mdd_to_csv_columns(isurveys))

        self.assertEqual((stats["applied"], stats["other_questions"], stats["unknown_ids"]), (5, 1, {9999}))
        self.assertEqual(df.loc[1001, "_ResName"], "An Nguyen")
        self.assertEqual(df.loc[1001, "_ResWardSelected"], "W2")
        self.assertEqual(df.loc[1002, "_ResPhone._C_1"], "0912345678")
        self.assertEqual(df.loc[1002, "BLOCK[_1].ADDR"], "new address")
        self.assertTrue(pd.isnull(df.loc[1002, "_ResName"]))
        self.assertEqual(list(df.columns), ["_ResName", "_ResPhone._C_1", "_ResWardSelected", "BLOCK[_1].ADDR"])
        self.assertEqual(list(df.index), [1001, 1002])

    def test_cancelled_respondents(self):
        from app.core.pipeline import cancelled_respondents

        df = pd.DataFrame({"_ResName": list("ABCDEF")}, index=pd.Index([1, 2, 3, 4, 5, 6], name="InstanceID"))
        loai_phieu = {"1": 1, "2": 3, "3": 1, "4": 3, "5": 1}   # CSV values; 6 has no _LoaiPhieu
        updates = pd.DataFrame([
            (3, "_LoaiPhieu", "{_1}", "{_3}"),   # cancelled through update_data.csv
            (4, "_loaiphieu", "{_3}", "{_1}"),   # un-cancelled through update_data.csv
            (5, "_LoaiPhieu", "{_1}", "{_13}"),
            (1, "Q5", "1", "{_3}"),              # another question
        ], columns=["InstanceID", "Question Name", "Previous Value", "Current Value"])

        self.assertEqual(cancelled_respondents(df, loai_phieu, updates), [2, 3])
        self.assertEqual(cancelled_respondents(df, loai_phieu, pd.DataFrame()), [2, 4])


def _variables():
    from app.core.update_check import VariableInfo, normalize_name
    variables = [
        VariableInfo("Q1", T.mtCategorical.value, ("_1", "_2", "_3"), min_value=1, max_value=1),
        VariableInfo("Q2", T.mtCategorical.value, ("_1", "_2", "_3", "_99"), frozenset({"_99"}), min_value=1),
        VariableInfo("Q3", T.mtCategorical.value, ("_1", "_2", "_3", "_4"), max_value=2),
        VariableInfo("AGE", T.mtLong.value, min_value=18, max_value=65),
        VariableInfo("SCORE", T.mtDouble.value),
        VariableInfo("NAME", T.mtText.value, max_value=5),
        VariableInfo("BLOCK[{_1}].ADDR", T.mtText.value),
        VariableInfo("VISIT", T.mtDate.value),
        VariableInfo("BLOCK", T.mtObject.value),
    ]
    return {normalize_name(v.name): v for v in variables}


def _updates(rows):
    return pd.DataFrame([(i, q, "", v) for i, q, v in rows],
                        columns=["InstanceID", "Question Name", "Previous Value", "Current Value"])


class UpdateCheckTest(unittest.TestCase):
    def check(self, rows, valid_ids=None):
        from app.core.update_check import check_update_rows
        return [(str(i.instance_id), i.question, i.level, i.message)
                for i in check_update_rows(_updates(rows), _variables(), valid_ids)]

    def test_valid_rows(self):
        self.assertEqual(self.check([
            (1, "Q1", "{_2}"), (1, "q2", "{_1,_3}"), (1, "Q2", "{_99}"), (1, "Q3", "{ _1 , _4 }"),
            (1, "AGE", "30"), (1, "SCORE", "-2.5"), (1, "NAME", "An"), (1, "block[_1].addr", "x"),
            (1, "VISIT", "2026-10-14 09:30:00"), (1, "Q1", np.nan), (1, "Q2", "{}"),
        ], valid_ids={"1"}), [])

    def test_code_not_in_the_metadata(self):
        self.assertEqual(self.check([(1, "Q1", "{_5}")]),
                         [("1", "Q1", "error", "code _5 not in the MDD categories (_1, _2, _3)")])

    def test_categorical_answer_rules(self):
        self.assertEqual([m for *_, m in self.check([
            (1, "Q1", "_2"), (1, "Q1", "{_1,_2}"), (1, "Q2", "{_1,_99}"), (1, "Q3", "{_1,_2,_3}"), (1, "Q2", "{_1,_1}"),
        ])], [
            "value _2 must be written as {_1} or {_1,_2}",
            "single-answer question: 2 codes given, only one allowed",
            "code _99 is exclusive and cannot be combined with other codes",
            "3 codes given, at most 2 allowed",
            "code _1 written more than once",
        ])

    def test_numbers_dates_and_text(self):
        self.assertEqual([(lvl, m) for *_, lvl, m in self.check([
            (1, "AGE", "abc"), (1, "AGE", "17"), (1, "AGE", "30.5"), (1, "SCORE", "x"),
            (1, "VISIT", "not a date"), (1, "NAME", "Nguyen"), (1, "BLOCK", "x"),
        ])], [
            ("error", "value abc is not a whole number"),
            ("error", "value 17 outside the MDD range 18..65"),
            ("error", "value 30.5 is not a whole number"),
            ("error", "value x is not a number"),
            ("error", "value not a date is not a date"),
            ("warning", "text of 6 characters, the MDD allows 5"),
            ("error", "BLOCK is not a question that holds a value (data type mtObject)"),
        ])

    def test_unknown_question_and_instance(self):
        self.assertEqual(self.check([(1, "Q9", "{_1}"), (2, "Q1", "{_1}"), (np.nan, "Q1", "{_1}"), (1, np.nan, "1")],
                                    valid_ids={"1"}), [
            ("1", "Q9", "error", "question Q9 does not exist in the MDD"),
            ("2", "Q1", "error", "InstanceID 2 is not in the data"),
            ("", "Q1", "error", "InstanceID is empty"),
            ("1", "", "error", "Question Name is empty"),
        ])

    def test_statements_follow_the_mdd_types(self):
        df = _updates([(1, "q1", "{_2}"), (1, "Q3", "{_1, _4}"), (1, "NAME", "O'Neil"), (1, "AGE", "30"),
                       (1, "block[_1].addr", "0912"), (2, "SCORE", np.nan)])
        self.assertEqual(dict(update_data_statements(df, _variables())), {
            1: "UPDATE VDATA SET Q1 = {_2},Q3 = {_1,_4},NAME = 'O''Neil',AGE = 30,BLOCK[{_1}].ADDR = '0912' WHERE InstanceID = 1",
            2: "UPDATE VDATA SET SCORE = NULL WHERE InstanceID = 2",
        })

    def test_report(self):
        from app.core.update_check import check_update_rows, write_report
        issues = check_update_rows(_updates([(1, "Q1", "{_5}")]), _variables())
        with tempfile.TemporaryDirectory() as tmp:
            report = pd.read_excel(write_report(issues, Path(tmp) / "logs" / "check.xlsx"))
        self.assertEqual(report.to_dict("records"), [{"InstanceID": 1, "Question Name": "Q1", "Current Value": "{_5}",
                                                      "Level": "error",
                                                      "Problem": "code _5 not in the MDD categories (_1, _2, _3)"}])


class AnswerSyntaxTest(unittest.TestCase):
    def test_three_level_groups_ending_with_a_nested_option(self):
        # Same shape as _PJ2 of VN2026221_IVORY: header > sub header > options, last option at level 3.
        from object.iSurvey import iAnswers

        layout = [("_H1", "", True), ("_H1_1", "1", True), ("_1", "2", False), ("_2", "2", False),
                  ("_H2", "", True), ("_H2_1", "5", True), ("_3", "6", False)]
        options = {}
        for pos, (name, group, is_header) in enumerate(layout, 1):
            options[str(pos)] = {
                "answersetreference": "", "is_sublist": is_header, "attributes": {"groupID": group},
                "syntax": f"{name} {{###sublist{pos}###}}" if is_header else name,
            }
        answers = iAnswers.__new__(iAnswers)
        answers["options"] = options
        self.assertEqual(answers.syntax(), "_H1 {_H1_1 {_1,_2}},_H2 {_H2_1 {_3}}")


def _valid_config():
    return {
        "project_name": "VN_TEST",
        "run_mdd_source": True,
        "source_initialization": {"default_language": "VIT"},
        "main": {"xmls": {"101": "main.xml"}, "protoid_final": "101"},
        "stages": {
            "stage-1": {"xmls": {"201": "s1.xml", "--Enter a protodid 2--": "--Enter a xml file 2--"}, "protoid_final": "201"},
            "stage-2": {"xmls": {"--Enter a protodid 1--": "--Enter a xml file 1--"}, "protoid_final": "--Enter a protodid finalize--"},
        },
    }


class ConfigTest(unittest.TestCase):
    def test_valid_config(self):
        self.assertEqual(validate_config(_valid_config()), [])

    def test_placeholders_are_skipped_in_stages(self):
        self.assertEqual(xml_mappings(_valid_config()["stages"]["stage-1"]), [("201", "s1.xml")])

    def test_errors(self):
        config = _valid_config()
        config["main"]["xmls"]["--Enter a protodid 2--"] = "--Enter a xml file 2--"
        config["main"]["protoid_final"] = "999"
        config["stages"]["stage-1"]["protoid_final"] = "202"
        messages = " | ".join(i.message for i in validate_config(config))
        self.assertIn("placeholder", messages)
        self.assertIn("999 is not listed", messages)
        self.assertIn("202 is not listed", messages)

    def test_template_config_is_rejected(self):
        from app.core import paths
        issues = validate_config(load_config(paths.project_template_dir() / "config.json"))
        self.assertTrue(has_errors(issues))


class ProjectTest(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.workspace, ignore_errors=True)

    def test_create_and_check_sources(self):
        project = create_project(self.workspace, "VN_TEST")
        self.assertEqual([p.name for p in list_projects(self.workspace)], ["VN_TEST"])
        self.assertEqual(load_config(project.config_path)["project_name"], "VN_TEST")
        with self.assertRaises(ConfigError):
            create_project(self.workspace, "VN_TEST")

        save_config(project.config_path, _valid_config())
        pd.DataFrame({"InstanceID": [1, 2, 3], "ProtoSurveyID": [101, 101, 555]}).to_csv(project.csv_dir / "a.csv", index=False)
        (project.xml_dir / "main.xml").write_text("<x/>", encoding="utf-8")

        scan, issues = scan_sources(project)
        self.assertEqual(scan.proto_rows, {101: 2, 555: 1})

        issues += check_sources(project, load_config(project.config_path), scan)
        messages = [str(i) for i in issues]
        self.assertIn("[ERROR] stages.stage-1: XML file not found: source\\xml\\s1.xml", messages)
        self.assertIn("[ERROR] stages.stage-1: ProtoID 201 has no data in the CSV files.", messages)
        self.assertTrue(any(m.startswith("[WARNING] ProtoID 555") for m in messages))


if __name__ == "__main__":
    unittest.main()
