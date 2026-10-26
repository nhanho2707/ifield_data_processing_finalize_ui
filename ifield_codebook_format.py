"""Map manual OE coding labels to codebook codes.

The logic lives in app/core/codebook.py; edit the values below and run this file.
Equivalent command:

    python -m app codebook "projects\\<project>\\data\\oe\\<file>.xlsx"
"""
from app.core import paths
from app.core.codebook import apply_codebook

project_name = "VN2024174_HAKOCHI_Q22024"

excel_filename = "Q9CD BATH 2 manual_report"

# Codebook columns: the label written to the output and the text searched in the coded labels.
label_column, match_column = "LABEL VNI", "TACTIC LABEL"
# label_column, match_column = "CHANNEL VNI", "LABEL VNI"
# label_column, match_column = "PRODUCT VIE", "LABEL VNI"

if __name__ == "__main__":
    excel_file = paths.default_workspace() / project_name / "data" / "oe" / f"{excel_filename}.xlsx"
    apply_codebook(excel_file, label_column=label_column, match_column=match_column)
