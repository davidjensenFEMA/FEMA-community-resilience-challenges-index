# -*- coding: utf-8 -*-
"""
Created on Fri Feb  4 13:57:18 2022

@author: jhutchison

conda install -c conda-forge mapclassify

"""

# %% Packages
""" Third party and local imports """

# import json
import numpy as np
import pandas as pd
import pathlib

# import requests

# Local Import
from utils.utils_logger import logger
from cria_create_indicators import ser_ref

from utils.utils_excel_table_save import table_save


# %% Functions
""" Define functions """


# %% Variables
""" Set local variables """

path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")

# details
run_occupied_houses = False

# results
d_res = {}

year_current = 2022
geography = "county"

logger.info(f"prep for {geography} during {year_current}")

idx_geo = ser_ref["geographies"][geography].index
idx_corr = ser_ref["ref"]["Label_Correlation"]
idx_features = ser_ref["ref"]["Indicator"]


# %% Data
""" Prep data for year to year comparison, save in series """

d_year = {
    "curr": year_current,
    "prev": year_current - 1,
}
ser_curr = pd.Series(dtype=object)

for label_year, year in d_year.items():
    if geography == "county":
        file_name = f"cria_results_{geography}_{year}"
    elif geography == "tract":
        file_name = f"impute_tract_data_match_county_{year}"
    # Pickle
    ser_data = pd.read_pickle(path_out / f"{file_name}.pkl")
    ser_data["agg"] = pd.Series(
        {
            "meta": ser_data["agg_meta"],
            "bins": ser_data["agg_labels"],
        }
    )
    ser_curr[f"data_{year}"] = ser_data["data"]
    ser_curr[f"df_{year}"] = ser_data["indicators"]
    ser_curr[f"agg_{year}"] = ser_data["agg"]
    ser_curr[f"corr_{year}"] = ser_data["corr"]
    ser_curr[f"bin_meta_{year}"] = ser_data["bin_meta"]

    d_res[f"data_{year}"] = ser_data["data"]
    d_res[f"df_{year}"] = ser_data["indicators"]
    d_res[f"agg_{year}"] = ser_data["agg"]
    d_res[f"corr_{year}"] = ser_data["corr"]


# %% Main
""" Demonstrate similarities year to year """

if __name__ == "__main__":
    corr_curr = ser_curr[f'corr_{d_year["curr"]}'].loc[idx_corr, idx_corr]
    corr_prev = ser_curr[f'corr_{d_year["prev"]}'].loc[idx_corr, idx_corr]

    # Correlation check
    ser_check = pd.Series(
        corr_curr.columns == corr_prev.columns,
        index=corr_curr.index,
    )

    logger.info(f"similar features /n{ser_check}")

    # check corr year to year
    # use location index to ensure matching indices
    corr_diff = corr_curr - corr_prev
    ser_check = corr_diff.round(2).max()

    logger.info(f"max differences between year to year corr \n{ser_check}")

    if ser_check.max() > 0.1:
        logger.info(f"check differences \n{ser_check.where(ser_check > 0.1).dropna()}")
    else:
        logger.info(f"minor differences year to year <= {ser_check.max()}")
    # d_res["corr_curr"] = corr_curr
    # d_res["corr_prev"] = corr_prev
    d_res["corr_diff"] = corr_diff

    # Aggregate check
    agg_curr = ser_curr[f'agg_{d_year["curr"]}']["bins"].rename(
        {"agg": f'agg_{d_year["curr"]}', "agg_bins": f'agg_bins_{d_year["curr"]}'},
        axis=1,
    )
    agg_prev = ser_curr[f'agg_{d_year["prev"]}']["bins"].rename(
        {"agg": f'agg_{d_year["prev"]}', "agg_bins": f'agg_bins_{d_year["prev"]}'},
        axis=1,
    )

    agg_diff = (
        agg_curr.loc[idx_geo, f'agg_{d_year["curr"]}']
        - agg_prev.loc[idx_geo, f'agg_{d_year["prev"]}']
    )

    check_diff = agg_diff.abs().sort_values(ascending=False)
    idx_diff = check_diff.index[:30]

    d_res["agg_diff"] = agg_diff.to_frame()

    df_diff_curr = ser_curr[f'df_{d_year["curr"]}'].loc[idx_diff, idx_features]
    df_diff_prev = ser_curr[f'df_{d_year["prev"]}'].loc[idx_diff, idx_features]
    df_diff = df_diff_curr - df_diff_prev
    logger.info(f"biggest agg diff by indicator \n{df_diff.describe().T}")

    ser_labels = ser_curr[f'data_{d_year["curr"]}'].loc["labels", :].dropna()
    idx_data_features = ser_labels.index

    data_diff_curr = ser_curr[f'data_{d_year["curr"]}'].loc[idx_diff, :]
    data_diff_prev = ser_curr[f'data_{d_year["prev"]}'].loc[idx_diff, :]
    idx_data_features = [
        feature
        for feature in idx_data_features
        if ((feature in data_diff_curr) and (feature in data_diff_prev))
    ]
    data_diff = data_diff_curr[idx_data_features] - data_diff_prev[idx_data_features]
    for feature in idx_data_features:
        data_diff[feature] = pd.to_numeric(data_diff[feature])
    check_data_diff = pd.concat([ser_labels, data_diff.describe().T], axis=1).dropna(
        axis=0, thresh=3
    )
    logger.info(f"biggest agg diff by indicator \n{check_data_diff}")

    # Check year to year agg

    pop_curr = (
        ser_curr[f'data_{d_year["curr"]}']
        .loc[agg_curr.index, "S0101_C01_001E"]
        .rename(f'pop_{d_year["curr"]}')
    )
    pop_prev = (
        ser_curr[f'data_{d_year["prev"]}']
        .loc[agg_curr.index, "S0101_C01_001E"]
        .rename(f'pop_{d_year["prev"]}')
    )

    check_agg = pd.concat(
        [
            agg_curr[[f'agg_{d_year["curr"]}', f'agg_bins_{d_year["curr"]}']],
            pop_curr,
            agg_prev[[f'agg_{d_year["prev"]}', f'agg_bins_{d_year["prev"]}']],
            pop_prev,
        ],
        axis=1,
    )
    pd.isna(check_agg).sum()
    idx_check = check_agg.loc[pd.isna(check_agg["pop_2021"]), :].index
    ser_curr["df_2021"].loc[idx_check, :]

    for col in check_agg.columns:
        check_agg[col] = pd.to_numeric(check_agg[col])

    check_agg_corr = check_agg.dropna(axis=0, how="any").corr()

    d_res["check_agg"] = check_agg
    d_res["check_agg_corr"] = check_agg_corr

    logger.info("comparison ready")

    # occupied houses check
    if run_occupied_houses:
        total_houses = ser_curr[f'data_{d_year["curr"]}']["DP04_0001E"].rename("total")
        occupied_houses = ser_curr[f'data_{d_year["curr"]}']["DP04_0002E"].rename(
            "occupied"
        )
        vacant_houses = (
            total_houses.loc[idx_geo] - occupied_houses.loc[idx_geo]
        ).rename("vacant")

        df_houses = pd.concat(
            [
                total_houses,
                occupied_houses,
                vacant_houses,
                occupied_houses.loc[idx_geo]
                .divide(total_houses.loc[idx_geo])
                .rename("Owner_Total"),
                ser_curr[f'df_{d_year["curr"]}']["Owner Occupied"],
                ser_curr[f'df_{d_year["curr"]}']["Age"],
                ser_curr[f'df_{d_year["curr"]}']["Low Access to Communications"],
                ser_curr[f'df_{d_year["curr"]}']["Disability"],
                ser_curr[f'df_{d_year["curr"]}']["Mobile Homes"],
            ],
            axis=1,
        )

        d_res["df_houses"] = df_houses.copy()

        df_houses = df_houses.loc[idx_geo, :].dropna(axis=0, how="any")

        for col in df_houses.columns:
            df_houses[col] = pd.to_numeric(df_houses[col])

        corr_houses = df_houses.corr()
        d_res["corr_houses"] = corr_houses

        df_houses[["Age", "Owner_Total", "Owner Occupied"]].plot(
            kind="scatter", x="Age", y="Owner Occupied"
        )
        df_houses[["Age", "Owner_Total", "Owner Occupied"]].plot(
            kind="scatter", x="Age", y="Owner_Total"
        )
        df_houses[["Age", "Owner_Total", "Owner Occupied"]].plot.scatter(
            x="Age", y="Owner_Total", c="Owner Occupied"
        )
        df_houses[["Age", "Owner_Total", "Owner Occupied"]].plot.scatter(
            x="Owner Occupied", y="Owner_Total", c="Age"
        )


# %% Bin Labels
""" compare binning methods """

bins_curr = ser_curr[f'bin_meta_{d_year["curr"]}']
bins_prev = ser_curr[f'bin_meta_{d_year["prev"]}']

df_bins = pd.concat(
    [
        bins_curr.loc["choose", :].T.rename(2021),
        bins_prev.loc["choose", :].T.rename(2020),
    ],
    axis=1,
)

list_idx = list(df_bins.index)
list_idx = [idx for idx in list_idx if idx[-4:] == "bins"]

df_bins = df_bins.loc[list_idx, :]

df_bins_full = pd.concat(
    [
        bins_curr.loc[
            ["choose", "group 1", "group 2", "group 3", "group 4", "group 5"], :
        ].T.rename(
            {
                "choose": 2021,
                "group 1": "2021_g1",
                "group 2": "2021_g2",
                "group 3": "2021_g3",
                "group 4": "2021_g4",
                "group 5": "2021_g5",
            },
            axis=1,
        ),
        bins_prev.loc[
            ["choose", "group 1", "group 2", "group 3", "group 4", "group 5"], :
        ].T.rename(
            {
                "choose": 2020,
                "group 1": "2020_g1",
                "group 2": "2020_g2",
                "group 3": "2020_g3",
                "group 4": "2020_g4",
                "group 5": "2020_g5",
            },
            axis=1,
        ),
    ],
    axis=1,
)

for group in range(1, 6):
    df_bins_full[f"g{group}_diff"] = (
        df_bins_full[f"2021_g{group}"] - df_bins_full[f"2020_g{group}"]
    )

df_bins_full["max_diff"] = (
    df_bins_full[[f"g{group}_diff" for group in range(1, 6)]].abs().max(axis=1)
)

d_res["df_bins"] = df_bins.reset_index().rename({"index": "indicator"}, axis=1)
d_res["df_bins_full"] = df_bins_full.reset_index().rename(
    {"index": "indicator"}, axis=1
)


# %% Write
""" Record results """

# file_name = f'cria_yoy_{geography}_{ser_ref["years"]["acs"]}'
file_name = f"cria_yoy_{geography}_{year_current}"
table_save(d_res, path_out / f"{file_name}.xlsx", keep_index=True)

logger.info("results ready")
