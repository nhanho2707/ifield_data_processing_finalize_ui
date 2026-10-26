import os
import sys
# sys.path.append(r'C:\Users\nhan.ho\ipsos_digital_transformation-main')
import re
import numpy as np
import pandas as pd
from tqdm import tqdm   # <-- New import
import win32com.client as w32
import shutil
from object.metadata import Metadata
from datetime import datetime 
from object.metadata import *
from object.spss import *

import collections.abc
#hyper needs the four following aliases to be done manually.
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping
collections.MutableSet = collections.abc.MutableSet
collections.MutableMapping = collections.abc.MutableMapping

#os.chdir("ipsos_digital_transformation")

mdd_path = r"projects\BIO_DIARY\data\PVN2025224_BIO_CLEAN_MERGE_v3.mdd"
ddf_path = r"projects\BIO_DIARY\data\PVN2025224_BIO_CLEAN_MERGE_v3.ddf"

sql_query = r"SELECT * FROM VDATA"
#   WHERE Respondent.ID = 2122714
#  WHERE _Cell_Recruit.ContainsAny({_16})"

questions = ["Respondent.ID","SHELL_BLOCK","_Quota_BUMO","_Cell_Recruit","_ResProvinces","_Phase"] 
m = Metadata(mdd_file=mdd_path, ddf_file=ddf_path, sql_query=sql_query)

df = m.convertToDataFrame(questions)

# df_1 = pd.DataFrame(data=SPSSObject_Dataframe.records, columns=SPSSObject_Dataframe.varNames)

cols = ["Respondent.ID","SHELL_INTERVIEWER_LOGIN","Quota_BUMO","Cell_Recruit","ResProvinces"]
cols.extend(c for c in df.columns if re.match(pattern=r"_Phase\[\{_([1-9]|1[0-9]|2[0-6])\}\]\.(_A0a|_A0c|_A2_start\._Date|_A2_start\._Time|_A2_end\._Date|_A2_end\._Time|_A5|_A3|_Phase_time)", string=c))
# cols.extend(c for c in df.columns if re.match(pattern=r"^(_QI_Codes)_\d+_\d+$", string=c))

df_temp = df[cols]
df_temp.set_index(["Respondent.ID","SHELL_INTERVIEWER_LOGIN","Quota_BUMO","Cell_Recruit","ResProvinces"], inplace=True)
#"_A3_Other_Text",

# liệt kê cột cần xuất data
qres = [
	r"_A0a",
	r"_A0c",
	r"_A2_start._Date",
	r"_A2_start._Time",
	r"_A2_end._Date",
	r"_A2_end._Time",
	r"_A5",
    r"_Phase_time[{_A0a}]._StartTime",
    r"_Phase_time[{_A0c}]._StartTime",
    r"_Phase_time[{_A2_start}]._StartTime",
    r"_Phase_time[{_A2_end}]._StartTime",
    r"_Phase_time[{_A3}]._StartTime",
    r"_Phase_time[{_A5}]._StartTime"
    ]

df_merge_1 = pd.DataFrame()

arr = ""

# For each q, merge the resulting data frame on common keys (including "Mieng")
for q in tqdm(qres, desc="Processing questions"):  # <-- Wrapped progress bar around qres loop
    pattern = r"^_Phase\[\{_([1-9]|1[0-9]|2[0-4])\}\]\." + re.escape(q) + r"$"
    cols = [c for c in df.columns if re.fullmatch(pattern, c)]
    
    df_qre = df_temp[cols].stack().reset_index().rename(columns={'level_5' : 'Mieng', 0 : q})
    # df_qre = df_temp[cols].dropna(axis=1, how='all').stack().reset_index().rename(columns={'level_5': 'Mieng', 0: q})
    df_qre["Mieng"] = df_qre["Mieng"].apply(
        lambda x: next((m for m in re.findall(r"\{_\d+\}", x)), "")
    )
    df_qre.set_index(["Respondent.ID","SHELL_INTERVIEWER_LOGIN","Quota_BUMO","Cell_Recruit","ResProvinces"], inplace=True)
    df_qre = df_qre.reset_index()  # reset index to include join keys
    
    # Merge with existing data (horizontally) by common keys including "Mieng"
    if df_merge_1.empty:
        df_merge_1 = df_qre.copy()
    else:
        df_merge_1 = pd.merge(df_merge_1, df_qre, 
                              on=["Respondent.ID","SHELL_INTERVIEWER_LOGIN","Quota_BUMO","Cell_Recruit","ResProvinces","Mieng"], 
                              how="outer")

# Sort by "Mieng": remove the "{_}" characters, convert to numbers, then sort ascending.
if 'Mieng' in df_merge_1.columns:   
    df_merge_1['Mieng_clean'] = df_merge_1['Mieng'].str.replace(r'[\{\}_]', '', regex=True)
    df_merge_1['Mieng_numeric'] = pd.to_numeric(df_merge_1['Mieng_clean'], errors='coerce')
    df_merge_1 = df_merge_1.sort_values('Mieng_numeric', ascending=True)
    df_merge_1.drop(columns=['Mieng_clean', 'Mieng_numeric'], inplace=True)

# After df_merge_1 has been sorted by Mieng (ascending)

# Ensure the _A0a column is available and check its ordering.
if '_A0a' in df_merge_1.columns:
    # Create a new error column with default empty string.
    df_merge_1["error"] = ""
    df_merge_1["error_A3"] = ""
    # Group by Respondent.ID.
    groups = list(df_merge_1.groupby("Respondent.ID"))
    for rid, group in tqdm(groups, desc="Checking respondent order"):
        # Clean the _A0a values (e.g. "{_1}" becomes "1") and convert to numeric.
        a0a_numeric = pd.to_numeric(group["_A0a"].str.replace(r"[^\d]", "", regex=True), errors="coerce")
        # Compute the cumulative maximum.
        cummax = a0a_numeric.cummax()
        # Flag rows where the current value is less than the cumulative maximum.
        error_mask = a0a_numeric < cummax
        if error_mask.any():
            # Update the error column for the rows in this group that are out of order.
            indices = group.index[error_mask]
            df_merge_1.loc[indices, "error"] = "Lỗi ngày không liên tục"


# Format date and time columns in one pass
if '_A2_start._Date' in df_merge_1.columns:
    df_merge_1['_A2_start._Date'] = pd.to_datetime(
        df_merge_1['_A2_start._Date'], format='%d/%m/%Y %H:%M:%S', errors='coerce'
    ).dt.strftime('%d/%m/%Y')

if '_A2_end._Date' in df_merge_1.columns:
    df_merge_1['_A2_end._Date'] = pd.to_datetime(
        df_merge_1['_A2_end._Date'], format='%d/%m/%Y %H:%M:%S', errors='coerce'
    ).dt.strftime('%d/%m/%Y')

if '_A2_start._Time' in df_merge_1.columns:
    df_merge_1['_A2_start._Time'] = pd.to_datetime(
        df_merge_1['_A2_start._Time'], format='%d/%m/%Y %H:%M:%S', errors='coerce'
    ).dt.strftime('%H:%M:%S')

if '_A2_end._Time' in df_merge_1.columns:
    df_merge_1['_A2_end._Time'] = pd.to_datetime(
        df_merge_1['_A2_end._Time'], format='%d/%m/%Y %H:%M:%S', errors='coerce'
    ).dt.strftime('%H:%M:%S')

# ---- Time gap validation between consecutive Mieng rows for each Respondent.ID ----
def combine_datetime(date_str, time_str):
    try:
        return pd.to_datetime(date_str + ' ' + time_str, format='%d/%m/%Y %H:%M:%S', errors='coerce')
    except Exception:
        return pd.NaT

for rid, group in df_merge_1.groupby("Respondent.ID"):
    # Sort group by numeric value in the 'Mieng' column.
    group_sorted = group.copy()
    group_sorted['Mieng_numeric'] = group_sorted['Mieng'].str.extract(r'(\d+)').astype(float)
    group_sorted = group_sorted.sort_values('Mieng_numeric')
    # Iterate over consecutive pairs (e.g. "{_1}" and "{_2}", "{_2}" and "{_3}", etc.)
    for i in range(len(group_sorted) - 1):
        row_current = group_sorted.iloc[i]
        row_next = group_sorted.iloc[i + 1]
        dt_end = combine_datetime(row_current.get('_A2_end._Date', ''), row_current.get('_A2_end._Time', ''))
        dt_start = combine_datetime(row_next.get('_A2_start._Date', ''), row_next.get('_A2_start._Time', ''))
        if pd.isnull(dt_end) or pd.isnull(dt_start):
            continue
        # Calculate the gap in minutes.
        gap_minutes = (dt_start - dt_end).total_seconds() / 60
        # If the gap is less than 0 or more than 30 minutes, then add/update the "error" column note.
        if (gap_minutes < 0) or (gap_minutes > 30):
            note = f"Lỗi thời gian (phút): {gap_minutes:.2f}"
            orig_error = row_next.get("error", "")  
            if orig_error:
                new_error = orig_error + ", " + note
            else:
                new_error = note
            df_merge_1.loc[row_next.name, "error"] = new_error
        # Nếu thời gian của Phasetime[{_A3]}]._StartTime giữa 2 miếng lớn hơn 2 tiếng báo lỗi ở cột mới error_A3
        dt_phasetime_next = pd.to_datetime(row_next.get('_Phase_time[{_A3}]._StartTime', ''), format='%d/%m/%Y %H:%M:%S', errors='coerce')
        dt_phasetime_cur = pd.to_datetime(row_current.get('_Phase_time[{_A3}]._StartTime', ''), format='%d/%m/%Y %H:%M:%S', errors='coerce')
        if pd.isnull(dt_phasetime_cur):
            continue
        gap_phasetime_minutes = (dt_phasetime_next - dt_phasetime_cur).total_seconds() / 60
        if gap_phasetime_minutes < 120:
            note = f"Lỗi thời gian Phasetime A3 (phút): {gap_phasetime_minutes:.2f}"
            orig_error = row_next.get("error_A3", "")
            if orig_error:
                new_error = orig_error + ", " + note
            else:
                new_error = note
            df_merge_1.loc[row_next.name, "error_A3"] = new_error
        

# Double numeric values for all columns except "error" and create new columns with suffix '_FW_UPDATE'
cols_to_double = [col for col in df_merge_1.columns if col != "error"]
for col in cols_to_double:
    df_merge_1[col + "_FW_UPDATE"] = np.nan

# ------------------- Export to Excel ---------------------
# Define the output file name before creating the writer.
file_name = f"PVN2025182_BIO_DIARY_BREAK_BY_PAD_{datetime.now().strftime('%Y%m%d')}.xlsx"

writer = pd.ExcelWriter(file_name, engine='xlsxwriter')
df_merge_1.to_excel(writer, index=False, sheet_name='Sheet1')
workbook = writer.book
worksheet = writer.sheets['Sheet1']

# # Format the header row.
# header_format = workbook.add_format({
#     'bold': True,
#     'text_wrap': True,
#     'valign': 'top',
#     'fg_color': '#D7E4BC',  # Light greenish background.
#     'border': 1
# })
# fw_header_format = workbook.add_format({
#     'bold': True,
#     'text_wrap': True,
#     'valign': 'top',
#     'fg_color': '#90EE90',  # Light green background.
#     'border': 1
# })
# for col_num, value in enumerate(df_merge_1.columns.values):
#     if value.endswith("_FW_UPDATE"):
#         worksheet.write(0, col_num, value, fw_header_format)
#     else:
#         worksheet.write(0, col_num, value, header_format)

# # Determine the range of the data, including header.
# max_row = df_merge_1.shape[0] + 1   # number of rows including header
# max_col = df_merge_1.shape[1]       # number of columns

# # Add an Excel table over the data range with a built-in table style.
# worksheet.add_table(0, 0, max_row - 1, max_col - 1,
#                       {
#                           'name': "Table1",
#                           'columns': [{'header': col} for col in df_merge_1.columns],
#                           'style': 'Table Style Medium 9'
#                       })

# Autofit columns by calculating the maximum width from the header and data.
for i, col in enumerate(df_merge_1.columns):
    column_len = max(df_merge_1[col].astype(str).map(len).max(), len(col)) + 2  # add extra margin
    worksheet.set_column(i, i, column_len)

writer.close()