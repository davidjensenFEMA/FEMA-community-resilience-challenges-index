# -*- coding: utf-8 -*-
"""
Created on Wed Jan 26 15:00:00 2023

@author: jhutchison
"""

# %% Packages
""" Third party and local imports """

# import json
# import matplotlib
import numpy as np
import pandas as pd
import pathlib

import matplotlib.pyplot as plt

# Local imports
from utils.utils_logger import logger

from cria_pull_data import ser_ref
from utils.utils_excel_table_save import table_save


# %% Functions
""" Define functions """


# %% Variables
""" Set local variables """

path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")

geographies = ser_ref["geographies"]

d_res = {}

# %% Load data
""" If necessary, collect additional data """

# link_nri = "https://hazards.fema.gov/nri/Content/StaticDocuments/DataDownload//NRI_Table_CensusTracts/NRI_Table_CensusTracts.zip"
# link_svi = "https://www.atsdr.cdc.gov/placeandhealth/svi/data_documentation_download.html"
# link_cejst = "https://screeningtool.geoplatform.gov/en/downloads#3/33.47/-97.5"

# link_asarb = "https://www.usreligioncensus.org/sites/default/files/"
# link_asarb += "2022-11/2020%20USRC%20Summaries.xlsx"

# xls = pd.ExcelFile(link_asarb)
# asarb = pd.read_excel(xls, sheet_name="2020 County Summary")


cejst = pd.read_csv(path_data / "1.0-communities.csv", low_memory=False)
# col_focus = "Identified as disadvantaged without considering neighbors"  # col Q
col_focus = "Identified as disadvantaged"  # col T
cejst["cejst"] = cejst[col_focus].copy()
logger.info(f"cejst shape {cejst.shape}, and count {cejst['cejst'].sum()}")

cejst["GEO_ID"] = "1400000US" + cejst["Census tract 2010 ID"].astype(str).str.pad(
    11, fillchar="0"
)
cejst.index = cejst["GEO_ID"]
cejst = cejst.merge(geographies["tract"], left_index=True, right_index=True, how="left")

svi = pd.read_csv(path_data / "SVI2020_US.csv", na_values=[-999])
svi["svi"] = svi["RPL_THEMES"].copy()
svi["GEO_ID"] = "1400000US" + svi["FIPS"].copy().astype(str).str.pad(11, fillchar="0")
svi.index = svi["GEO_ID"]
logger.info(f"svi shape {svi.shape}, and \n{svi['svi'].describe()}")
svi = svi.merge(geographies["tract"], left_index=True, right_index=True, how="left")

nri = pd.read_csv(path_data / "NRI_Table_CensusTracts.csv")
nri["GEO_ID"] = "1400000US" + nri["TRACTFIPS"].copy().astype(str).str.pad(
    11, fillchar="0"
)
nri.index = nri["GEO_ID"]
check = list(nri.columns)

d_cols = {
    "POPULATION": "nri_pop",
    "BUILDVALUE": "nri_val_bldg",
    "AGRIVALUE": "nri_val_ag",
    "AREA": "nri_area",
    "RISK_SCORE": "nri_score",
    "RISK_RATNG": "nri_rating",  # these monsters don't spell "ing"
    # "RISK_NPCTL": "nri_p",
    "RISK_VALUE": "nri_value",
    "EAL_SCORE": "eal_score",
    "EAL_RATNG": "eal_rating",
    "EAL_VALT": "eal_valt",  # total composite
    "EAL_VALB": "eal_valb",  # bulding value
    "EAL_VALP": "eal_valp",  # population
    "EAL_VALPE": "eal_valpe",  # population equivalence
    "EAL_VALA": "eal_vala",  # agriculture value
    # "EAL_NPCTL": "eal_p",
    "SOVI_SCORE": "sovi_score",
    "SOVI_RATNG": "sovi_rating",
    # "SOVI_VALUE": "sovi_value",
    # "SOVI_NPCTL": "sovi_p",
    "RESL_SCORE": "resl_score",
    "RESL_RATNG": "resl_rating",
    "RESL_VALUE": "resl_value",
    # "RESL_NPCTL": "resl_p",
}

nri = nri[d_cols.keys()].rename(d_cols, axis=1)
nri.shape
nri.info()
nri.describe()

geography = "county"
file_name = f'cria_results_{geography}_{ser_ref["years"]["acs"]}'
ser_data_county = pd.read_pickle(path_out / f"{file_name}.pkl")

cri = ser_data_county["agg_labels"].copy()
pd.isna(cri).sum()
cri["cri"] = cri["agg"]

geography = "tract"
method = "match_county"
file_name = f'impute_tract_data_{method}_{ser_ref["years"]["acs"]}'
ser_data = pd.read_pickle(path_out / f"{file_name}.pkl")

cri = ser_data["agg_labels"].copy()
pd.isna(cri).sum()
# cri["cri"] = cri["agg"]


logger.info(f"cri shape {cri.shape}, and \n{cri['cri'].describe()}")
cri = cri.merge(geographies["tract"], left_index=True, right_index=True, how="left")


# %% Data
""" Load data from reference """

col_focus = "Identified as disadvantaged"  # col T
cejst["cejst"] = cejst[col_focus].copy()

col_focus = "RPL_THEMES"
svi["svi"] = svi[col_focus].copy()

cri["cri_p"] = cri["cria_p"].copy()

data = pd.concat(
    [
        geographies["tract"].copy(),
        cejst["cejst"],
        svi["svi"],
        cri["cri_p"],
        cri["cri"],
        nri,
    ],
    axis=1,
)

data["nri_factor"] = data["sovi_score"] / data["resl_score"]
data["nri_proxy_val"] = data["eal_score"] * data["nri_factor"]
# nri["nri_proxy_val"] =

# data[["nri_factor", "cri"]].plot()

data["nri_proxy_score"] = (
    100
    * (data["nri_proxy_val"] - data["nri_proxy_val"].min())
    / (data["nri_proxy_val"].max() - data["nri_proxy_val"].min())
)


logger.info(f"na values are an issue \n{pd.isna(data).sum()}")
logger.info(
    f'unmatched cri and svi: {(pd.isna(data["cri"]) != pd.isna(data["svi"])).sum()}'
)
logger.info(
    f'unmatched cejst and svi: {(pd.isna(data["cejst"]) != pd.isna(data["svi"])).sum()}'
)
logger.info(
    f'unmatched cejst and cri: {(pd.isna(data["cejst"]) != pd.isna(data["cri"])).sum()}'
)

d_res["data"] = data
d_res["na_values"] = pd.isna(data).sum().to_frame()


# %% Bin values
""" Add categorical values for comparison """

list_bins_svi = [-999, 0.6, 0.8, 999]
data["svi_bins"] = pd.cut(
    data["svi"],
    bins=list_bins_svi,
    labels=range(1, len(list_bins_svi)),
)
data.groupby("svi_bins")["svi_bins"].count()

# list_bins_cria_5 = [-999, -1, -0.5, 0, 1, 999]  # current
# list_bins_cria_7 = [-999, -1.5, -1, -0.5, 0, 1, 1.5, 999]  # current actual
# list_bins_cria_7 = [-999, -2.5, -1.5, -0.5, 0.5, 1.5, 2.5, 999]  # current RAPT
list_bins_cria_7 = [-999, -1.25, -0.75, -0.25, 0.25, 0.75, 1.25, 999]  # proposed
list_bins_cria_5 = [-999, -0.75, -0.25, 0.25, 0.75, 999]  # proposed

col_cut = "cri"
list_cut = list_bins_cria_7
data["cri_bins"] = pd.cut(
    data[col_cut],
    bins=list_cut,
    labels=range(1, len(list_cut)),
)
check_cri_7 = data.groupby("cri_bins")["cri"].agg(["min", "max", "count"])
logger.info(f"\n{check_cri_7}")
check_cri_7.round(3).to_clipboard()

# data["cri_bins"].hist()

# list_bins_cria_5 = [-999, -1, -0.5, 0, 1, 999]

# col_cut = "cri"
# list_cut = list_bins_cria_5
# data["cri_bins"] = pd.cut(
#     data[col_cut],
#     bins=list_cut,
#     labels=range(1, len(list_cut)),
# )
# check_cri_5 = data.groupby("cri_bins")["cri"].agg(["min", "max", "count"])
# logger.info(f"\n{check_cri_5}")
# check_cri_5.round(3).to_clipboard()


# # list_bins_cria_p = [-999, 0.6, 0.8, 999]
# list_bins_cria_p = [-999, 0.2, 0.4, 0.6, 0.8, 999]
# col_cut = "cri_p"
# list_cut = list_bins_cria_p
# data["cri_bins"] = pd.cut(
#     data[col_cut],
#     bins=list_cut,
#     labels=range(1, len(list_cut)),
# )

# check_cri_p = data.groupby("cri_bins")["cri"].agg([min, max])
# logger.info(f"\n{check_cri_p}")
# # cri["cri_bins"].hist()

# check = data.groupby(["cejst", "svi_bins", "cri_bins"])["cri"].agg([min, max])


# %% Address NA and Location
""" Remove NA values, merge location data """


df = data.drop(geographies["tract"].columns, axis=1).copy()

df.groupby(["cejst"])[["svi", "cri_p", "cri"]].describe().T
data.groupby(["cejst"])[["svi", "cri_p", "cri"]].describe().T

data.groupby("region")["cejst"].sum()

data.groupby(["region", "cejst"])[["cejst", "svi", "cri"]].agg(
    {"cejst": "count", "svi": np.mean, "cri": np.mean}
)
data.groupby(["region", "cejst"])[["cejst", "svi", "cri"]].describe()

data.groupby(["state", "cejst"])[["cejst", "svi", "cri"]].agg(
    {"cejst": "count", "svi": np.mean, "cri": np.mean}
).merge(
    geographies["state"][["NAME", "state"]],
    right_on="state",
    left_on="state",
)

df["svi_bins"] = pd.to_numeric(df["svi_bins"])
df["cri_bins"] = pd.to_numeric(df["cri_bins"])
df[["cejst", "svi_bins", "cri_bins"]].corr()

df_counts = df.groupby(["cejst", "svi_bins", "cri_bins"])["cri"].count()
df_counts = df_counts.reset_index().rename({"cri": "count"}, axis=1)
logger.debug(f"\n{df_counts}")


count = df_counts.where(
    (df_counts["cejst"] == 1)
    & (df_counts["svi_bins"] > 0)
    & (df_counts["cri_bins"] > 0)
)["count"]
str_log = "highly vulnerable across multiple indices"
logger.info(f'{str_log} {count.sum() / df_counts["count"].sum() * 100:.2f}%')

df_counts["rate"] = df_counts["count"] / df_counts["count"].sum()

d_res["cejst_sri_cri"] = df_counts

df_svi_cri = df.groupby(["svi_bins", "cri_bins"])["cri"].count()
df_svi_cri = df_svi_cri.reset_index().rename({"cri": "count"}, axis=1)
df_svi_cri["rate"] = df_svi_cri["count"] / df_svi_cri["count"].sum()

d_res["svi_cri"] = df_svi_cri

df_svi = df.groupby(["svi_bins"])["cri"].count()
df_svi = df_svi.reset_index().rename({"cri": "count"}, axis=1)
df_svi["rate"] = df_svi["count"] / df_svi["count"].sum()

d_res["svi"] = df_svi


df_svi_cejst_true = df.where(df["cejst"] == 1).groupby(["svi_bins"])["cri"].count()
df_svi_cejst_true = df_svi_cejst_true.reset_index().rename({"cri": "count"}, axis=1)
df_svi_cejst_true["rate"] = (
    df_svi_cejst_true["count"] / df_svi_cejst_true["count"].sum()
)

logger.info(f"svi where cejst is true \n{df_svi_cejst_true}")

# %% Final Out
""" Final out, amend correlation """

# data["sovi_resl"] = data["sovi_value"] / data["resl_value"]
data["svi_resl"] = data["svi"] / data["resl_value"]

# cols_corr = [
#     "cejst",
#     "nri_score",
#     "eal_score",
#     "svi",
#     "sovi_score",
#     "resl_score",
#     "sovi_resl",
#     "svi_resl",
#     "cri",
# ]

cols_corr = [
    "cri",
    "svi",
    "resl_value",
    "svi_resl",
]

d_cols_rev = {val: key for key, val in d_cols.items()}
d_cols_rev["cri"] = "CRI"
d_cols_rev["svi"] = "SVI"
d_cols_rev["svi_resl"] = "SVI / RESL"

df = data[cols_corr].copy().rename(d_cols_rev, axis=1)
# df["cejst"] = pd.to_numeric(data["cejst"])
df = df.dropna(axis=0, how="any")

corr_matrix = df.corr().round(3)
d_res["corr_simple"] = corr_matrix

d_res["df_describe"] = df.describe().T

# %% Population
""" Add population """

# df_pop = df.merge(cri["Total_Population"], left_index=True, right_index=True).rename(
#     {"Total_Population": "pop"}, axis=1
# )

# pd.cut(
#     df_pop["pop"],
#     bins=len(list_bins_cria_p),
#     # labels=range(1, len(list_bins_cria_p)+1),
# )

# df_pop["pop_bins"] = pd.cut(
#     df_pop["pop"],
#     bins=len(list_bins_cria_p),
#     labels=range(1, len(list_bins_cria_p) + 1),
# )
# df_pop["pop_bins"] = pd.to_numeric(df_pop["pop_bins"])
# corr_pop = df_pop[["pop_bins", "cejst", "svi_bins", "cri_bins"]].corr().round(3)
# d_res["corr_pop"] = corr_pop

# data = data.merge(cri["Total_Population"], left_index=True, right_index=True).rename(
#     {"Total_Population": "pop"}, axis=1
# )


# %% Main
""" Demonstrate """

if __name__ == "__main__":
    # geography = "county"
    # logger.info(f"cri indicators ready at {geography} level")
    d_res["data"] = data
    logger.info("comparison ready")

    cols = [
        "cejst",
        "nri_score",
        "eal_score",
        "svi",
        "sovi_score",
        "resl_score",
        # "sovi_resl",
        "svi_resl",
        "cri",
    ]

    df = data[cols].copy()
    df.plot.scatter(x="cri", y="svi")
    df.plot.scatter(x="cri", y="resl_score")
    df.plot.scatter(x="cri", y="nri_score")
    df.plot.scatter(x="cri", y="svi_resl")

    df.plot.hist(column=["resl_score"], bins=75)


file_name = "cri_index_comparison"
table_save(d_res, path_out / f"{file_name}.xlsx", keep_index=True)

ser_data = pd.Series(d_res)
ser_data.to_pickle(path_out / f"{file_name}.pkl")

# %%
