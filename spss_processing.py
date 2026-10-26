"""Export an MDD/DDF of one project to SPSS .sav.

The logic lives in app/core/spss_export.py; edit the values below and run this file.
Equivalent command:

    python -m app spss <project> --mdd <mdd> --ddf <ddf> -q Q1 Q2 ...
"""
from app.core import paths
from app.core.project import open_project
from app.core.spss_export import export_spss

project_name = "VN2025037_YODA_2023_2024"

mdd_file = "data\\JTI_VNM_Consumer_Tracker_20250206_QV2_V2_EXPORT.mdd"
ddf_file = "data\\JTI_VNM_Consumer_Tracker_20250206_QV2_V2_EXPORT.ddf"

# sql_query = "SELECT * FROM VDATA WHERE Respondent_serial = '6823050106491224' OR Respondent_serial = '6823050106491225'"
sql_query = "SELECT * FROM VDATA"

questions = [
    "Respondent_serial", 
    "Hidden_COUNTRY",
    "COUNTRY_ID",
    "Year",
    "QUARTER",
    "QVERSION",
    "WTVAR",
    "TGT_SAMPLE",
    "P_GEN",
    "P_AGE",
    "Hidden_P_AGE_CAT",
    "P_REG",
    "P_URB_RUR",
    "P_OCC",
    "P_EDU",
    "Hidden_P_EDU",
    "Hidden_P_OCC",
    "Hidden_P_OCC_DET",
    "P_HHCONST",
    "LQ_VNM_P_SEC_INC_HH_VTN",
    "C_RMC_RYO_MYO_ADC",
    "UBAW1_RMC",
    "UBAW2_RMC",
    "CJ_RMC_UMB_ABAW",
    "CJ_RMC_SKU_ABAW",
    "CJ_RMC_UMB_REG",
    "CJ_RMC_SKU_REG",
    "CJ_RMC_SKU_REG_TIME",
    "CJ_RMC_SKU_SMO_MONTH",
    "CJ_RMC_SKU_TRI",
    "CJ_RMC_SKU_CON",
    "CJ_RMC_SKU_PREV",
    "CJ_RMC_SKU_REG_SWITCH",
    "CJ_RMC_SKU_SHARE",
    "CJ_RMC_SKU_ADV",
    "BI_RMC_SKU",
    "PI_RMC_SKU",
    "SEG_1",
    "SEG_2",
    "SEG_4",
    "SEG_5",
    "SEG_6",
    "SEG_7",
    "SEG_8",
    "SEG_9",
    "SEG_10",
    "SEG_11",
    "SEG_12",
    "SEGMENTS",
    "SEGMENTS_V21",
    "DEMAND_SPACES_DS6",
    "DEMAND_SPACES_DS7"
]

if __name__ == "__main__":
    project = open_project(paths.default_workspace(), project_name)
    export_spss(project, mdd_file, ddf_file, questions, sql_query)

# Earlier wide-to-long experiment on SPSSObject.df_spss (object/spss.py), kept for reference:
# cols = [col for col in spssObject.df_spss.columns if re.match(pattern=f"(CJ_RMC_SKU_TOTCON|CJ_RMC_SKU_REP|CJ_RMC_SKU_TOTTRI)_C\d+", string=col) ]

# df_1 = spssObject.df_spss.drop(columns=cols)

# stubnames = [
# "BI_RMC_10_SKU_C11",
# "BI_RMC_10_SKU_C15",
# "BI_RMC_10_SKU_C1",
# "BI_RMC_10_SKU_C13",
# "BI_RMC_10_SKU_C6",
# "BI_RMC_10_SKU_C14",
# "BI_RMC_10_SKU_C33",
# "BI_RMC_10_SKU_C22",
# "BI_RMC_10_SKU_C27",
# "BI_RMC_10_SKU_C19",
# "BI_RMC_10_SKU_C46",
# "BI_RMC_10_SKU_C3",
# "BI_RMC_10_SKU_C17",
# "BI_RMC_10_SKU_C4",
# "BI_RMC_10_SKU_C7",
# "BI_RMC_10_SKU_C12",
# "BI_RMC_10_SKU_C35",
# "BI_RMC_10_SKU_C36",
# "BI_RMC_10_SKU_C24",
# "BI_RMC_10_SKU_C99",
# "BI_RMC_10_SKU_ByConsider_C11",
# "BI_RMC_10_SKU_ByConsider_C15",
# "BI_RMC_10_SKU_ByConsider_C1",
# "BI_RMC_10_SKU_ByConsider_C13",
# "BI_RMC_10_SKU_ByConsider_C6",
# "BI_RMC_10_SKU_ByConsider_C14",
# "BI_RMC_10_SKU_ByConsider_C33",
# "BI_RMC_10_SKU_ByConsider_C22",
# "BI_RMC_10_SKU_ByConsider_C27",
# "BI_RMC_10_SKU_ByConsider_C19",
# "BI_RMC_10_SKU_ByConsider_C46",
# "BI_RMC_10_SKU_ByConsider_C3",
# "BI_RMC_10_SKU_ByConsider_C17",
# "BI_RMC_10_SKU_ByConsider_C4",
# "BI_RMC_10_SKU_ByConsider_C7",
# "BI_RMC_10_SKU_ByConsider_C12",
# "BI_RMC_10_SKU_ByConsider_C35",
# "BI_RMC_10_SKU_ByConsider_C36",
# "BI_RMC_10_SKU_ByConsider_C24",
# "BI_RMC_10_SKU_ByConsider_C99",
# "PI_RMC_10_SKU_C1",
# "PI_RMC_10_SKU_C4",
# "PI_RMC_10_SKU_C8",
# "PI_RMC_10_SKU_C2",
# "PI_RMC_10_SKU_C16",
# "PI_RMC_10_SKU_C3",
# "PI_RMC_10_SKU_C12",
# "PI_RMC_10_SKU_C7",
# "PI_RMC_10_SKU_C17",
# "PI_RMC_10_SKU_C19",
# "PI_RMC_10_SKU_C11",
# "PI_RMC_10_SKU_C20",
# "PI_RMC_10_SKU_C21",
# "PI_RMC_10_SKU_C99",
# "PI_RMC_10_SKU_ByConsider_C1",
# "PI_RMC_10_SKU_ByConsider_C4",
# "PI_RMC_10_SKU_ByConsider_C8",
# "PI_RMC_10_SKU_ByConsider_C2",
# "PI_RMC_10_SKU_ByConsider_C16",
# "PI_RMC_10_SKU_ByConsider_C3",
# "PI_RMC_10_SKU_ByConsider_C12",
# "PI_RMC_10_SKU_ByConsider_C7",
# "PI_RMC_10_SKU_ByConsider_C17",
# "PI_RMC_10_SKU_ByConsider_C19",
# "PI_RMC_10_SKU_ByConsider_C11",
# "PI_RMC_10_SKU_ByConsider_C20",
# "PI_RMC_10_SKU_ByConsider_C21",
# "PI_RMC_10_SKU_ByConsider_C99"
# ]

# i = ["Respondent.Serial","Hidden_COUNTRY","P_REG","VNM_TGT_01","P_AGE","Hidden_P_AGE_CAT","Hidden_P_AGE_GEN","CJ_SKU_REG_PRICE","CJ_SKU_REG_ORIGIN","P_OCC"]

# df_1_long = pd.wide_to_long(
#     df_1,
#     stubnames = stubnames,
#     i = i,
#     j = "Brand",
#     sep="_C",
#     suffix=r"\d+$"
# )

# cols = ["Respondent.Serial","Hidden_COUNTRY","P_REG","VNM_TGT_01","P_AGE","Hidden_P_AGE_CAT","Hidden_P_AGE_GEN","CJ_SKU_REG_PRICE","CJ_SKU_REG_ORIGIN","P_OCC"] + cols

# df_2 = spssObject.df_spss[cols]
# df_2 = df_2.drop(columns=["CJ_RMC_SKU_TOTCON_C99","CJ_RMC_SKU_REP_C99","CJ_RMC_SKU_TOTTRI_C99"])

# df_2_long = pd.wide_to_long(
#     df_2,
#     stubnames = ["CJ_RMC_SKU_TOTCON","CJ_RMC_SKU_REP","CJ_RMC_SKU_TOTTRI"],
#     i = i,
#     j = "Brand",
#     sep="_C",
#     suffix=r"\d+$"
# )

# df_long = pd.concat([df_2_long, df_1_long], ignore_index=False, axis=1)


# df_long.to_csv("abc.csv", encoding="utf-8")
