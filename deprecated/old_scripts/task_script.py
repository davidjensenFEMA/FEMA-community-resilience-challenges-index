# -*- coding: utf-8 -*-
"""
Created on Thursday Sep 14 12:00:00 2023

@author: jhutchison

mamba install -c conda-forge pandas numpy numba
    \mapclassify requests pathlib python=3.11


"""

# %% Packages
""" Third party and local imports """

import argparse
import pathlib
import pandas as pd
import numpy as np

# Local import
from utils.utils_logger import logger

from cria_functions import clean_series, fit_data


# %% Functions
""" Define functions """


# %% Variables
""" Set script (global) variables """

# Path Library
path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")

# Establish argument parser functionality
# Define the argument parser
try:
    logger.info("parsing args")
    parser = argparse.ArgumentParser(description="Bin one indicator per node.")

    parser.add_argument(
        "--idx_column", type=int, default=0, help="Index for indicator column."
    )
    parser.add_argument(
        "--run_test", type=bool, default=False, help="Whether to run in test mode."
    )

    # Parse the arguments
    args = parser.parse_args()

except:
    logger.info("arg parser failed")
    # running with interactive kernel: args errors
    pass


# %% Binning support
""" Set binning properties (script specific local variables) """

bins = {"county": 5, "tract": 7, "tribal": 5, "state": 5}
exceptions = {
    "county": {
        "Civil Org": ["Jenks Caspall"],
        "Hospitals": ["Jenks Caspall"],
        "Medical": ["Jenks Caspall"],
    },
    "tract": {
        "Mobile Homes": ["Jenks Caspall", "Fisher Jenks"],
        "Limited English": ["Jenks Caspall", "Fisher Jenks"],
        "Poverty": ["Jenks Caspall", "Fisher Jenks"],
        "Hospitals": ["Jenks Caspall", "Fisher Jenks"],
    },
    "tribal": {
        "Limited English": ["Jenks Caspall"],
    },
    "state": {},
}


# %% Data
""" Read tract data from pickle """

geography = "tract"

file_name = "impute_tract_data_match_county_2022"
ser_imp = pd.read_pickle(path_data / f"{file_name}.pkl")

file_name = "ser_geo"
ser_geo = pd.read_pickle(path_data / f"{file_name}.pkl")

# references
years = ser_imp["years"][0].to_dict()
ref = ser_imp["ref"]
geographies = ser_geo.copy()

df = ser_imp["indicators"][ref["Indicator"]]


"""Analyze CRIA data"""
# Prep
# Bin all features, county and tract
df_clean = df.apply(clean_series, impute=True)
if geography in ["state", "county", "tract"]:
    geo_ref = geographies[geography]
    idx_PR = geo_ref.loc[geo_ref["state"] == 72, :].index
    df_clean.loc[idx_PR, "Limited English"] = [np.nan] * len(idx_PR)

df_reshape = pd.DataFrame(
    data=df_clean, index=geographies[geography].index, columns=df_clean.columns
)
logger.debug("indicators cleaned")

# Rescale inputs, record as df_scale
# with few exceptions, want inputs scaled 0 to 100 rather than 0 to 1
rescale = ref.loc[ref["Units"].isin(["index", "fraction"]), "Indicator"]
logger.debug(f"rescaling {len(rescale)} columns")
df_scale = df_reshape.copy(deep=True)
df_scale[rescale] = 100 * df_scale[rescale]
logger.info(df_scale.shape)

# %% Main
""" Display task data """

if __name__ == "__main__":
    # print(f"i am python script #{args.idx_corpus_file}")
    try:
        idx_column = args.idx_column - 1  # zero index in python
        # run_test = args.run_test
        run_test = False
    except:
        idx_column = 0
        run_test = False

    indicator = ref.loc[idx_column, "Indicator"]
    # Use paramaters to reshape data
    if run_test:
        test_size = 50
        df_scale = df_scale.iloc[:50, :]

    ser_adj = df_scale.iloc[:, idx_column].copy(deep=True)
    df_adj = ser_adj.to_frame()
    logger.info(f"{indicator} {df_adj.shape}")
    # Bin indicators
    bin_results = fit_data(
        df_fit=df_adj,
        list_exceptions=exceptions[geography],
        groups=bins[geography],
    )

    if geography == "county":
        file_name = f'cria_results_{geography}_{years["acs"]}'
    elif geography == "tract":
        method = "match_county"
        file_name = f"impute_tract_data_{method}_{years['acs']}"
    if run_test:
        file_name = f"test_{file_name}"
    bin_results.to_pickle(path_out / f"{file_name}_hpc_{idx_column:02}.pkl")

    logger.info(f"{indicator} complete")
