"""Map manual OE coding labels to codebook codes (formerly ifield_codebook_format.py)."""
import re
from pathlib import Path

import pandas as pd

from app.core.errors import SourceError
from app.core.reporter import ConsoleReporter, Reporter


def apply_codebook(excel_file: Path, *, label_column: str = "LABEL VNI", match_column: str = "TACTIC LABEL",
                   code_column: str = "CODE", overview_sheet: str = "manual_Code_Overview",
                   punch_sheet: str = "manual_Code_Punch", respondent_column: str = "RESPONDENTID",
                   reporter: Reporter | None = None) -> Path:
    """For every label_<n> column of the punch sheet, add label_<n>_ipsos = (code, label).

    The first codebook row whose `match_column` text is contained (case-insensitive) in the
    coded label wins. Writes <excel name>_coding.xlsx next to the input file.
    Other codebook layouts: label_column="CHANNEL VNI", match_column="LABEL VNI", ...
    """
    reporter = reporter or ConsoleReporter()
    excel_file = Path(excel_file)
    if not excel_file.is_file():
        raise SourceError(f"File not found: {excel_file}")

    df = pd.read_excel(excel_file, engine="openpyxl", sheet_name=overview_sheet)
    missing = [c for c in (code_column, label_column, match_column) if c not in df.columns]
    if missing:
        raise SourceError(f"Sheet {overview_sheet} has no column {', '.join(missing)}.")

    codebook = [(code, label, str(match).lower())
                for code, label, match in df[[code_column, label_column, match_column]].fillna("").itertuples(index=False)]

    df_coding = pd.read_excel(excel_file, engine="openpyxl", sheet_name=punch_sheet)
    df_coding.set_index([respondent_column], inplace=True)

    unmatched = set()

    def lookup(text):
        if pd.isnull(text):
            return text
        for code, label, match in codebook:
            if match in text.lower():
                return (code, label)
        unmatched.add(text)
        return None

    label_columns = [c for c in df_coding.columns if re.match(pattern=r"label_\d+", string=c)]
    for column in reporter.progress(label_columns, "Map labels to codes"):
        df_coding[f"{column}_ipsos"] = df_coding[column].apply(lookup)

    for text in sorted(unmatched):
        reporter.warning(f"No codebook entry matches: {text}")

    output = excel_file.with_name(f"{excel_file.stem}_coding.xlsx")
    with pd.ExcelWriter(output, engine="xlsxwriter", mode="w") as writer:
        df_coding.to_excel(writer, sheet_name=punch_sheet)
    reporter.info(f"Saved {output}")
    return output
