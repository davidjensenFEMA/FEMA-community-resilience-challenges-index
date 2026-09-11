# -*- coding: utf-8 -*-
"""
Created on Wed Jan 26 15:00:00 2023

@author: jhutchison
"""

# %% Packages
""" Third party and local imports """

# import json
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pathlib
import seaborn as sns

from sklearn.cluster import KMeans
from sklearn.preprocessing import OneHotEncoder

# Local imports
from utils.utils_logger import logger
from utils.utils_api import create_geoid

from cria_pull_data import ser_ref
from utils.utils_excel_table_save import table_save


# %% Functions
""" Define functions """


# %% Variables
""" Set local variables """

path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")

geography = "county"

geographies = ser_ref["geographies"]

col_pop = "S0101_C01_001E"
col_med_income = "S1903_C03_001E"

d_cols_update = {
    "cri": "crci",
    "cria_p": "crci_P",
    col_pop: "tot_pop",
    col_med_income: "med_income",
}

geographies = ser_ref["geographies"]


# %% Data
""" Load data from reference """

if geography == "tract":
    method = "match_county"
    file_name = f'impute_tract_data_{method}_{ser_ref["years"]["acs"]}'
    ser_data = pd.read_pickle(path_out / f"{file_name}.pkl")
elif geography == "county":
    file_name = f'cria_results_{geography}_{ser_ref["years"]["acs"]}'
    ser_data = pd.read_pickle(path_out / f"{file_name}.pkl")

    file_name = "2020_UA_COUNTY.xlsx"
    xl = pd.ExcelFile(path_data / file_name)
    xl.sheet_names
    dfs = {sh.lower(): xl.parse(sh) for sh in xl.sheet_names}
    urban_areas = dfs["2020_ua_county"]
    urban_area_labels = dfs["fielddescriptions"].set_index("Field Name")[
        "Field Description"
    ]
    urban_area_labels.index = [idx.lower() for idx in urban_area_labels.index]
    urban_areas["GEO_ID"] = create_geoid(
        state=urban_areas["STATE"], county=urban_areas["COUNTY"]
    )
    urban_areas = urban_areas.set_index("GEO_ID", drop=True)
    urban_areas.columns = [col.lower() for col in urban_areas.columns]

    ser_data["urban_areas"], ser_data["urban_area_labels"] = (
        urban_areas,
        urban_area_labels,
    )

# Store and drop data labels
data_crci = ser_data["data"]
ser_data_labels = data_crci.loc["labels", :]
data_crci = data_crci.drop("labels", axis=0)

# Prep pop and income data
ser_pop = data_crci[col_pop]
ser_income = data_crci[col_med_income]

# Prep crci data
crci = ser_data["agg_labels"]

# Prep geo data
cols_geo = list(geographies[geography].columns)
cols_geo.append("name_abbr")
data_lowest_ind = ser_data["lowest_ind"].drop(cols_geo, axis=1)
data_scores_p = ser_data["scores_percentiles"].drop(cols_geo, axis=1)
data_scores = ser_data["scores"].drop(cols_geo, axis=1)

df_crci = pd.concat(
    [crci, ser_pop, ser_income, data_lowest_ind, data_scores], axis=1
).rename(d_cols_update, axis=1)


# %% Median income NA issues
""" There are issues with NA values in median income for tracts """

if geography == "tract":
    cols_check = ["med_income", "state_name", "county_name", "tract_name", "tot_pop"]
elif geography == "county":
    cols_check = ["med_income", "state_name", "county_name", "tot_pop"]

# For NA tracts, check AL
df_crci.loc[
    pd.isna(df_crci["med_income"]),
    cols_check,
].loc[df_crci["state_name"] == "Alabama"]

# For NA tracts, check max pop by state
df_crci.loc[
    pd.isna(df_crci["med_income"]),
    cols_check,
].groupby(
    "state_name"
)["tot_pop"].max()

# For NA tracts, check max pop for all tracts
df_crci.loc[pd.isna(df_crci["med_income"]), ["tot_pop"]].max()

# For available tracts, check min pop by state
# Drop "med_income" from cols_check
df_crci.dropna(axis=0, subset="med_income")[cols_check[1:]].groupby("state_name")[
    "tot_pop"
].min()

# For available tracts, check min pop for all tracts
df_crci.dropna(axis=0, subset="med_income")[["tot_pop"]].min()


# %% Main
""" Demonstrate """

if __name__ == "__main__":
    logger.info("data ready")

    k = 5
    cols_cluster = ["crci", "tot_pop", "med_income"]
    df_cluster = df_crci[cols_cluster].dropna(axis=0, subset="med_income")
    df_cluster = df_cluster.apply(pd.to_numeric)
    df_cluster.info()
    X = df_cluster
    kmeans = KMeans(n_clusters=k, random_state=101, n_init="auto").fit(X)
    kmeans.labels_
    kmeans.cluster_centers_

    df_cluster["bins"] = kmeans.labels_

    agg = df_cluster.groupby("bins")[["crci", "tot_pop", "med_income"]].agg(
        {
            "crci": ["count", "mean", "std", "min", "max"],
            "tot_pop": ["count", "mean", "std", "min", "max"],
            "med_income": ["count", "mean", "std", "min", "max"],
        }
    )
    agg.T

    file_name = f"crci_{geography}_analysis {k=}_groups"
    out = agg
    table_save(
        {"out": out.set_axis(agg.columns.map("_".join), axis=1).T},
        path_out / f"{file_name}.xlsx",
        keep_index=True,
    )

    # ser_data = pd.Series(out)
    # ser_data.to_pickle(path_out / f"{file_name}.pkl")

    cols_cat = ["ind_1", "ind_2", "ind_3"]
    df_cat = df_crci.dropna(axis=0, subset="med_income")[cols_cat]
    # df = df.apply(pd.to_numeric)
    df_cat.info()
    enc = OneHotEncoder(handle_unknown="ignore", sparse_output=False)

    # enc.fit_transform(df_cat).shape
    # enc = enc.fit(df_cat)
    # enc.categories_
    # list_pairs = list(zip(enc.categories_[0], range(1, len(enc.categories_[0])+1)))

    list_names = [
        f"{issue}_{cat}"
        for issue in range(1, 4)
        for cat in enc.fit(df_cat).categories_[0]
    ]
    df_cat = pd.DataFrame(
        enc.fit_transform(df_cat), columns=list_names, index=df_cluster.index
    )
    df = pd.concat([df_cluster.drop("bins", axis=1), df_cat], axis=1)

    cols_indicator = df_crci["ind_1"].dropna().unique()
    for cat in cols_indicator:
        # break
        cols = [f"{val}_{cat}" for val in range(1, 4)]
        df[cat] = df[cols].sum(axis=1)
        df = df.drop(cols, axis=1)
    # enc.inverse_transform([[0, 1, 1, 0, 0], [0, 0, 0, 1, 0]])
    # enc.get_feature_names_out(['Age', 'Uninsured Population'])

    k = 11
    X = df
    kmeans = KMeans(n_clusters=k, random_state=101, n_init="auto").fit(X)
    kmeans.labels_
    kmeans.cluster_centers_

    df["bins"] = kmeans.labels_

    list_cols = list(df.columns)
    list_cols.remove("bins")

    # [f(x) if condition else g(x) for x in sequence]
    # [<Exp1> if condition else <Exp2> if condition else <Exp3> for <item> in <iterable>]
    # { (some_key if condition else default_key):(something_if_true if condition
    #       else something_if_false) for key, value in dict_.items() }

    d_agg = {
        col: (
            ["count", "sum", "mean"]
            if col in ["crci", "tot_pop", "med_income"]
            else ["mean"]
        )
        for col in list_cols
    }

    agg = df.groupby("bins")[list_cols].agg(d_agg)
    df = df.merge(geographies[geography], left_index=True, right_index=True)

    agg.T

    logger.info(
        f"dropped {df_crci.shape[0] - X.shape[0]} rows from df_crci (med_income)"
    )

# %% Questions
""" Specific questions/concerns """
# What are the indicators that are most often in the top 3 challenges?
# What are the Counts for how often they each appear?
filter_crci_p = 0.8
top_challenges = (
    df.loc[df["crci"] > filter_crci_p, cols_indicator]
    .sum(axis=0)
    .sort_values(ascending=False)
)
logger.info(f"total \n{top_challenges}")


df_challenge = (
    df[cols_indicator]
    .reset_index(drop=False)
    .melt(
        id_vars="GEO_ID",
        value_vars=cols_indicator,
    )
)

df_score = (
    df_crci[cols_indicator]
    .reset_index(drop=False)
    .melt(
        id_vars="GEO_ID",
        value_vars=cols_indicator,
    )
)

df_ind = pd.merge(
    df_challenge,
    df_score,
    how="left",
    left_on=["GEO_ID", "variable"],
    right_on=["GEO_ID", "variable"],
    suffixes=["_challenge", "_scores"],
)
df_ind = pd.merge(
    df_ind,
    df_crci[["crci", "med_income", "tot_pop"]],
    left_on="GEO_ID",
    right_index=True,
)

df_ind = df_ind.sort_values(
    by=["variable"], key=lambda x: x.map(top_challenges), ascending=False
)

import sklearn.preprocessing

df_ind["tot_pop_cs"] = sklearn.preprocessing.scale(df_ind["tot_pop"])
df_ind["tot_pop_bin"] = pd.qcut(
    x=pd.to_numeric(df_ind["tot_pop"]),
    q=3,
    # labels=range(5)
)


# df_ind = df_ind.sort_values("value_scores")

# agg_ind = df_ind.drop_duplicates("GEO_ID", keep="first")

markers = {0: "o", 1: "X"}

sns.relplot(
    data=df_ind,
    x="crci",
    y="value_scores",
    hue="value_challenge",
    markers=markers,
    style="value_challenge",
    size="tot_pop_bin",
    sizes=[20, 60, 120],
    col="variable",
    kind="scatter",
)
plt.show()

for indicator in top_challenges.index:
    sns.scatterplot(
        data=df_ind.loc[df_ind["variable"] == indicator, :],
        x="crci",
        y="value_scores",
        hue="value_challenge",
        markers=markers,
        style="value_challenge",
        size="tot_pop_bin",
        sizes=[20, 40, 60],
        # ax="variable",
    ).set(title=f"{indicator} Scores Compared to CRCI")
    plt.show()


for indicator in top_challenges.index:
    sns.scatterplot(
        data=df_ind.loc[df_ind["variable"] == indicator, :],
        x="crci",
        y="value_scores",
        hue="value_challenge",
        # kind="swarm",
        # col="variable",
    ).set(title=f"{indicator} Scores Compared to CRCI")
    plt.show()

sns.catplot(
    data=df_ind,
    x="variable",
    y="value_scores",
    hue="value_challenge",
    kind="box",
    # col="variable",
).set(ylim=[0, 1], title=f"Indicator Scores")
plt.xticks(rotation=45, ha="right")
plt.show()

# sns.catplot(
#     data=df_ind,
#     x="value_scores",
#     y="variable",
#     hue="value_challenge",
#     kind="swarm",
#     # col="variable",
# ).set(ylim=[0, 1], title=f"Indicator Scores")
# plt.xticks(rotation=45, ha="right")
# plt.show()

# If I were a state and wanted to know the top 3 challenges for counties in my state – could I do that?

filter_state = "Virginia"
agg_state = df.groupby("state_name")[cols_indicator].sum()

logger.info(
    f"challenges to VA: \n{agg_state.loc[filter_state, :].T.sort_values(ascending=False)}"
)

# For counties with low population (less than 10,000) what are the most typical top 3 challenges?


filter_pop = 10000
top_challenges = (
    df.loc[df["tot_pop"] < filter_pop, cols_indicator]
    .sum(axis=0)
    .sort_values(ascending=False)
)
logger.info(f"filter population \n{top_challenges}")

# Can I get a list of counties that have those top 3 challenges?
top_3_challenges = top_challenges[:3].index
logger.info(f"top 3 challenges {top_3_challenges}")
logger.info(f"list counties{df.loc[df[top_3_challenges].sum(axis=1)==3].index}")
logger.info(f"list counties{df.loc[df[top_3_challenges].sum(axis=1)>=2].index}")


# For counties with dense populations, what are the most typical top 3 challenges?
if geography == "county":
    urban_area_labels["poppct_urb"]
    ser_pop_dens = urban_areas["poppct_urb"]
    filter_pop_dens = 0.5

    top_challenges = (
        df.loc[ser_pop_dens < filter_pop_dens, cols_indicator]
        .sum(axis=0)
        .sort_values(ascending=False)
    )
    logger.info(f"filter pop dens \n{top_challenges}")

    # Can I get a list of counties that have those challenges?
    # Or 2 out of 3 of those challenges?

    top_3_challenges = top_challenges[:3].index
    logger.info(f"top 3 challenges {top_3_challenges}")
    logger.info(f"list counties{df.loc[df[top_3_challenges].sum(axis=1)==3].index}")
    logger.info(f"list counties{df.loc[df[top_3_challenges].sum(axis=1)>=2].index}")


# %% Write
""" Write output """

file_name = f"crci_{geography}_analysis {k=}_groups"
out = agg.copy().set_axis(agg.columns.map("_".join), axis=1)

d_out = {
    "bin_labels": out,
    "meta": out.drop(
        [
            col
            for col in out.columns
            if col.startswith(("crci_mean", "tot_pop_mean", "med_income_mean")) == 0
        ],
        axis=1,
    ),
    "meta_corr": out.drop(
        [
            col
            for col in out.columns
            if col.startswith(("crci_mean", "tot_pop_mean", "med_income_mean")) == 0
        ],
        axis=1,
    ).corr(),
    "indicators": out.drop(
        [
            col
            for col in out.columns
            if col.startswith(("crci", "tot_pop", "med_income")) == 1
        ],
        axis=1,
    ),
    "indicators_corr": out.drop(
        [
            col
            for col in out.columns
            if col.startswith(("crci", "tot_pop", "med_income")) == 1
        ],
        axis=1,
    ).corr(),
    "bin_ind_corr": out.drop(
        [
            col
            for col in out.columns
            if col.startswith(("crci", "tot_pop", "med_income")) == 1
        ],
        axis=1,
    ).T.corr(),
    "df": df,
    "df_corr": df.drop(geographies[geography].columns, axis=1).corr(),
}

table_save(
    d_out,
    path_out / f"{file_name}.xlsx",
    keep_index=True,
)


# %% Old Code
""" Archive """
