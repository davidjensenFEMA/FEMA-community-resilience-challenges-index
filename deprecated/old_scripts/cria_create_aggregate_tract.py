# -*- coding: utf-8 -*-
"""
Created on Fri Feb  4 13:57:18 2022

@author: jhutchison

conda create --name conda_env_cria python=3.10.4
conda activate conda_env_cria
conda install -c conda-forge mapclassify
conda install -c conda-forge pyomo
conda install keras
conda install -c conda-forge tensorflow  # req python 3.9
conda install -c anaconda scikit-learn
conda install -c anaconda requests
mamba install openpyxl=3.1.0
conda install -c conda-forge xlsxwriter
"""

# %% Packages

# import json
import numpy as np
import pandas as pd
import pathlib

# import requests

# Local Import
from utils.utils_logger import logger

from cria_create_indicators import ser_ref, create_indicators
from cria_create_aggregate_indicator import create_agg_indicator

# from utils.utils_excel_table_save import table_save
from utils.utils_excel_tools import update_excel_workbook, save_excel_table


# %% Variables

path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")
path_reports = pathlib.Path(path_out / "reports/")


run_update_all_data = True

lowest_resilience = True

years = ser_ref["years"]
ref = ser_ref["ref"]
geographies = ser_ref["geographies"]


# %% Create State Aggregate
# Build plan
method = "match_county"
# method = "population_ratio"

# exceptions = {
#     "county": {
#         "Civil Org": "Jenks Caspall",
#         "Hospitals": "Jenks Caspall",
#         "Medical": "Jenks Caspall",
#     },
#     "tract": {
#         "Hospitals": "Jenks Caspall",
#         "Mobile Homes": ["Fisher Jenks", "Jenks Caspall"],
#     },
# }

# exceptions = {
#     "county": {
#         "Civil Org": "Jenks Caspall",
#         "Hospitals": "Jenks Caspall",
#         "Medical": "Jenks Caspall",
#     },
#     "tract": {
#         "Mobile Homes": ["Jenks Caspall", "Fisher Jenks"],
#         "Limited English": ["Jenks Caspall", "Fisher Jenks"],
#         "Poverty": ["Jenks Caspall", "Fisher Jenks"],
#         "Hospitals": ["Jenks Caspall", "Fisher Jenks"],
#     },
#     "tribal": {
#         "Limited English": ["Jenks Caspall"],
#     },
#     "state": {},
# }

exceptions = {
    "county": {
        "Civil Org": "Jenks Caspall",
        "Hospitals": "Jenks Caspall",
        "Medical": "Jenks Caspall",
    },
    "tract": {
        "Mobile Homes": ["Jenks Caspall", "Fisher Jenks"],
        "Limited English": ["Jenks Caspall", "Fisher Jenks"],
        "Poverty": [],
        "Hospitals": ["Jenks Caspall", "Fisher Jenks"],
    },
    "tribal": {
        "Limited English": ["Jenks Caspall"],
    },
    "state": {},
}

states = geographies["state"]
counties = geographies["county"]
tracts = geographies["tract"]
tribes = geographies["tribal"]

file_name = "all_data"

if run_update_all_data:
    for geography in ["state", "county", "tract"]:
        logger.info(f"beginning {geography}")
        df, data = create_indicators(ser_ref, geography=geography)
        labels = data.loc["labels", :].copy(deep=True)
        labels = labels.to_frame().T
        data = data.drop("labels", axis=0)
        geographies[f"df_{geography}"] = df
        geographies[f"data_{geography}"] = data
    geographies["labels"] = labels

    save_excel_table(geographies, path_data / f"{file_name}.xlsx", keep_index=True)
    data_ser = pd.Series(geographies).copy(deep=True)
    data_ser.to_pickle(path_data / f"{file_name}.pkl")

else:
    data_ser = pd.read_pickle(path_data / f"{file_name}.pkl")
    labels = data_ser["labels"]


# %% Continue here
""" Label as local variables """
# Reload data
data_state = data_ser["data_state"].copy(deep=True)
data_county = data_ser["data_county"].copy(deep=True)
data_tract = data_ser["data_tract"].copy(deep=True)

df_state = data_ser["df_state"].copy(deep=True)
df_county = data_ser["df_county"].copy(deep=True)
df_tract = data_ser["df_tract"].copy(deep=True)

missing_states = ref.loc[ref["Source"] != "ACS", "Indicator"]


# %% Complete state data, augment with agg county
""" Calculate state values """

# new columns include a _num in data; drop those cols
list_inputs = [col for col in list(data_county.columns) if str(col)[-3:] != "num"]
labels = labels[list_inputs]

data_county_aug = data_county.merge(
    counties, left_index=True, right_on="GEO_ID", how="outer"
)

agg_county = data_county_aug.groupby(["state"])[list_inputs].sum()

# Don't sum "index" values
cols = ref.loc[ref["Units"] == "index", "numerator"].to_list()
agg_county[cols] = (
    data_state[cols]
    .merge(states[["state"]], left_index=True, right_index=True)
    .set_index("state")
)

# Add GEO_ID to aggregate, but drop State in merge
agg_county = agg_county.merge(
    states.reset_index().loc[:, ["GEO_ID", "state"]],
    left_index=True,
    right_on="state",
    suffixes=[None, "_ref"],
)
agg_county = agg_county.set_index("GEO_ID")
# agg_county = agg_county.drop("state_ref", axis=1)
agg_county = agg_county.drop("state", axis=1)
agg_county.loc["labels", list_inputs] = labels.loc["labels", list_inputs]

df_state_aug, data_state_aug_ref = create_indicators(
    ser_ref, ser_data=pd.Series({"data": agg_county}), geography="state"
)
data_state_aug_ref = data_state_aug_ref.drop("labels", axis=0)


# %% Outer Joins on state
""" Join data into single tables """

data_tract = tracts.merge(data_tract, left_index=True, right_index=True, how="left")
data_county = counties.merge(data_county, left_index=True, right_index=True, how="left")
data_state = states.merge(
    data_state_aug_ref, left_index=True, right_index=True, how="left"
)

data_t = data_tract.merge(df_tract, left_index=True, right_index=True, how="left")
data_c = data_county.merge(df_county, left_index=True, right_index=True, how="left")
data_s = data_state.merge(df_state_aug, left_index=True, right_index=True, how="left")


# %% Super Table
""" Create final/main table """

cols_state = [f"{col}_state" for col in data_s.columns]
data_s.columns = cols_state
data_s["state_state"] = data_s["state_state"].astype(float)

cols_county = [f"{col}_county" for col in data_c.columns]
data_c.columns = cols_county
data_c[["state_county", "county_county"]] = data_c[
    ["state_county", "county_county"]
].astype(float)

cols_tract = [f"{col}_tract" for col in data_t.columns]
data_t.columns = cols_tract
data_t[["state_tract", "county_tract"]] = data_t[
    ["state_tract", "county_tract"]
].astype(float)

data = data_t.merge(
    data_c,
    left_on=["state_tract", "county_tract"],
    right_on=["state_county", "county_county"],
    suffixes=("_tract", "_county"),
    how="left",
)

data = data.merge(
    data_s,
    left_on="state_tract",
    right_on="state_state",
    suffixes=(None, "_state"),
    how="left",
)

data.index = tracts.index

# data.to_excel("data/detailed_table.xlsx")
# table_save({"all_cria": data},
#            "data/detailed_data.xlsx",
#            keep_index=True)
# data.to_pickle("data/detailed_data.pkl")
# logger.info("detailed_data ready")
# data = pd.read_pickle("data/detailed_data.pkl")


# %% Impute tract from county, no changes
""" Impute tract from county, no modification """

cols_imputed = []

df_t_imp = pd.DataFrame(
    data=data_ser["df_tract"], index=tracts.index, columns=data_ser["df_tract"].columns
)
df_t_imp_record = df_t_imp.copy(deep=True)
# if a column is unknown (based on source), then rewrite as np.nan
non_acs = ref.loc[ref["Source"] != "ACS", :]
cols_unknown = ref.loc[ref["Source"] != "ACS", "Indicator"]

for col in cols_unknown:
    df_t_imp[col] = [np.nan] * len(df_t_imp.index)
    df_t_imp_record[col] = pd.isna(df_t_imp[col])
    col_county = f"{col}_county"
    col_tract = f"{col}_tract"
    logger.debug(f"{col}: {pd.isna(df_t_imp[col]).sum()} reset")
    df_t_imp.loc[:, col] = data.loc[:, col_county]
# aggregate
data_t_imp = data_ser["data_tract"].copy(deep=True)
data_t_adj = pd.DataFrame(
    data=data_t_imp, index=tracts.index, columns=data_t_imp.columns
)
data_t_adj.loc["labels", list_inputs] = labels.loc["labels", list_inputs]

data_ser_imp = pd.Series({"data": data_t_adj, "df": df_t_imp})
d = create_agg_indicator(
    exceptions=exceptions,
    ser_ref=ser_ref,
    ser_data=data_ser_imp,
    geography="tract",
    bin_indicators=True,
)
d["labels"] = labels
d["impute_tract_record"] = df_t_imp_record


#### Modify empty vote data here
votes_by_state = data_county[["A1a", "A1c", "state_abbr"]].groupby("state_abbr").sum()
votes_by_state["prod"] = votes_by_state["A1a"] * votes_by_state["A1c"]

votes_by_state = pd.merge(
    left=votes_by_state,
    right=geographies["state"][["state", "state_abbr"]],
    left_index=True,
    right_on="state_abbr",
).sort_index()

zero_votes = votes_by_state.loc[votes_by_state["prod"] == 0]

df_bin_labels = d["bin_labels"].copy(deep=True)
df_bin_labels[["Inactive Voter_bins", "state_abbr"]].head()


states_with_zero = set(zero_votes["state_abbr"])

# Replace imputed values with np.nan where state_abbr is in the zero_votes list.
df_bin_labels.loc[
    df_bin_labels["state_abbr"].isin(states_with_zero), "Inactive Voter_bins"
] = np.nan

d["bin_labels"] = df_bin_labels
#### End Modify empty vote data

# %% Write
""" Record output Excel and pickle """

file_name = f"impute_tract_data_{method}_{years['acs']}"
save_excel_table(d, path_out / f"{file_name}.xlsx", keep_index=True)
data_ser_imp = pd.Series(d).copy(deep=True)
data_ser_imp.to_pickle(path_out / f"{file_name}.pkl")

method = "match_county"
file_name = f"impute_tract_data_{method}_{years['acs']}"
ser_data = pd.read_pickle(path_out / f"{file_name}.pkl")

geography = "tract"
file_name = f"Correlation Matrix {geography.upper()}"

list_ignore_sheet_names = ["Correlation Matrix", "Data"]
update_excel_workbook(
    file_name=f"{path_reports / file_name}.xlsx",
    ser_data=ser_data,
    list_ignore_sheet_names=list_ignore_sheet_names,
)


# %% Old Code
""" Old code """

# Population Ratios on Detailed Data
# data["population_ratio"] = data["S0101_C01_001E_tract"] / \
#     data["S0101_C01_001E_county"]
# data["population_ratio"].head()
# non_acs = ref.loc[ref["Source"] != "ACS", :]
# cols_known = ref.loc[ref["Source"] == "ACS",
#                      ["numerator", "denominator"]].apply(set)
# # flatten arrays
# cols_known = [item for sublist in cols_known for item in sublist]
# # find unique values in arrays, filter integers
# cols_known = [col for col in set(cols_known) if type(col) == str]
# # split lists
# cols_known = [col.split(", ") for col in cols_known]
# # flatten to final list form
# cols_known = [item for sublist in cols_known for item in sublist]

# =============================================================================
# for idx in non_acs.index:
#     ser = non_acs.loc[idx, :]
#     num = ser["numerator"]
#     if num == "NETMIG2019":
#         year_pop = 2019
#         num = [f"NETMIG{year}" for year in range(year_pop, year_pop-5, -1)]
#     else:
#         num = [num]
#     denom = [ser["denominator"]]
#     indicator = ser["Indicator"]
#     list_cols = [item for sublist in [num, denom] for item in sublist]
#     cols_county = [f"{col}_county" for col in list_cols]
#     data[cols_county].head()
#     cols_tract = [f"{col}_tract" for col in list_cols]
#     data[cols_tract].head()
#     cols_update = [col for col in list_cols if col not in cols_known]
#     for col in cols_update:
#         logger.debug(f"{indicator}, {col}")
#         col_tract = f"{col}_tract"
#         col_county = f"{col}_county"
#         if method == "match_county":
#             logger.info("method is to match county inputs")
#             data.loc[tracts.index, col_tract] = \
#                 data.loc[tracts.index, col_county]
#         elif method == "population_ratio":
#             data[col_tract] = data[col_county] * data["population_ratio"]
#         data[col_tract].head()
#         data.loc[data[col_tract].dropna().index, col_tract] = \
#             data.loc[data[col_tract].dropna().index, col_tract]\
#             .apply(round, 0)
#         data[col_tract].head()
#         # update tract dataframe
#         cols_imputed.append(col_tract)
#         data_t_imp[col] = data[col_tract]
#         logger.debug(f"{col} added to cols_imputed")
#         # Check outputs, aggregate tract to county against county
#         # data[[col_tract, col_county, "county_tract", "state_tract"]]\
#         #     .groupby(["county_tract", "state_tract"])[col_tract].sum()
# =============================================================================

# =============================================================================
# # %% Impute from population ratio
# # Record all imputed values
# cols_imputed = []
# # data_t_imp = data_ser["data_tract"].copy(deep=True).loc[tracts.index, :]
# data_t_imp = data_ser["data_tract"].copy(deep=True)
# data_t_imp_record = data_t_imp.copy(deep=True)
# # if a column is unknown (based on source), then rewrite as np.nan
# non_acs = ref.loc[ref["Source"] != "ACS", :]
# cols_known = ref.loc[ref["Source"] == "ACS",
#                      ["numerator", "denominator"]].apply(set)
# # flatten arrays
# cols_known = [item for sublist in cols_known for item in sublist]
# # find unique values in arrays, filter integers
# cols_known = [col for col in set(cols_known) if type(col) == str]
# # split lists
# cols_known = [col.split(", ") for col in cols_known]
# # flatten to final list form
# cols_known = [item for sublist in cols_known for item in sublist]
# for col in data_t_imp:
#     if col == 813410:
#         break
#     if col not in cols_known:
#         data_t_imp[col] = [np.nan]*len(data_t_imp.index)
#     col_county = f"{col}_county"
#     col_tract = f"{col}_tract"
#     data_t_imp_record[col] = pd.isna(data_t_imp[col])
#     logger.debug(f"{col} {pd.isna(data_t_imp[col]).sum()}")
#     data_t_imp.loc[pd.isna(data_t_imp[col]), col] = \
#         data.loc[pd.isna(data_t_imp[col]), col_county]
# # use updated data to calc tract indicators and agg indicator
# data_t_imp = data_t_imp.loc[tracts.index, :]
# data_t_imp_record = data_t_imp_record.loc[tracts.index, :]
# data_t_imp = data_t_imp.apply(pd.to_numeric)
# data_t_imp.loc["labels", :] = labels
# # data_t_imp.loc["labels", :] = labels.loc["labels", :]
# df_tract_imp, data_tract_imp = \
#     create_indicators(data_ser=pd.Series({"data": data_t_imp}))
# data_ser_imp = pd.Series({"data": data_tract_imp, "df": df_tract_imp})
# # exceptions = {"tract": df_tract_imp.columns}
# d = create_agg_indicator(data_ser_imp, geography="tract",
#                          exceptions=exceptions)
# d["labels"] = labels.to_frame().T
# d["impute_tract_record"] = data_t_imp_record
# file_name = f"data/impute_tract_data_{method}"
# table_save(d, f"{file_name}.xlsx", keep_index=True)
# data_ser_imp = pd.Series(d).copy(deep=True)
# data_ser_imp.to_pickle(f"{file_name}.pkl")
# =============================================================================
