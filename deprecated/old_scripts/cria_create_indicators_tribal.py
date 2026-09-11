# -*- coding: utf-8 -*-
"""
Created on Fri Feb  4 13:57:18 2022

@author: jhutchison
"""

# %% Packages
""" Third party and local imports """

# import json
import numpy as np
import pandas as pd
import pathlib

# import requests

# Local Import
from cria_create_indicators import ser_ref, create_indicators
from cria_functions import clean_series, fit_data

from utils.utils_excel_table_save import table_save
from utils.utils_logger import logger


# %% Variables
""" Set local variables """

path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")

lowest_resilience = True

# years = ser_ref["years"]
ref = ser_ref["ref"]
geographies = ser_ref["geographies"]


# %% Binning support
""" Set binning properties (script specific local variables) """

bins = {"county": 5, "tract": 7, "tribal": 5}

issues = {"county": [], "tract": [], "tribal": []}

# jenks caspall struggles with some inputs;
# save calculation time by skipping these indicators

exceptions = {
    "county": {
        "Civil Org": ["Jenks Caspall"],
        "Hospitals": ["Jenks Caspall"],
        "Medical": ["Jenks Caspall"],
    },
    "tract": {
        "Mobile Homes": ["Jenks Caspall"],
        "Limited English": ["Jenks Caspall"],
        "Inactive Voter": ["Equal Interval"],
    },
    "tribal": {
        "Limited English": ["Jenks Caspall"],
        "Medical": ["Jenks Caspall"],
    },
}


# %% Functions
""" Define functions """


# %% Main
""" Retrieve data, calc indicators, aggregate, save """


"""*** Modify here ***
Highlight tribes with 0 population
Remove 0pop tribes from df prior to binning
One NA label
Add tribes back to final report
***"""


if __name__ == "__main__":
    geography = "tribal"
    df, data = create_indicators(ser_ref, ser_data=None, geography=geography)
    logger.info(f"cria indicators ready at {geography} level")
    # Excel
    d = {"cria_indicators": df, "cria_inputs": data}
    file_name = f'cria_indicators_{geography}_{ser_ref["years"]["acs"]}'
    table_save(d, path_out / f"{file_name}.xlsx", keep_index=True)
    # Pickle
    ser_data = pd.Series({"data": data, "df": df})
    ser_data.to_pickle(path_out / f"{file_name}.pkl")

    cols_unknown = ref.loc[ref["Source"] != "ACS", "Indicator"]
    df = df.drop(cols_unknown, axis=1)
    df_tribal = pd.DataFrame(df, index=ser_ref["geographies"]["tribal"].index)
    # df = df.dropna(axis=0, how="all")

    df_clean = df.apply(clean_series, impute=False)
    # df_clean = df_clean.loc[check_index[geography], :]
    df_reshape = pd.DataFrame(
        data=df_clean, index=geographies[geography].index, columns=df_clean.columns
    )
    logger.debug("indicators cleaned")

    # Rescale inputs, record as df_scale
    # with few exceptions, want inputs scaled 0 to 100 rather than 0 to 1
    rescale = ref.loc[ref["Units"].isin(["index", "fraction"]), "Indicator"]
    rescale_tribal = [col for col in rescale.values if col not in cols_unknown.values]
    logger.debug(f"rescaling {len(rescale_tribal)} columns")
    df_scale = df_reshape.copy(deep=True)
    df_scale[rescale_tribal] = 100 * df_scale[rescale_tribal]
    # Bin indicators

    ser_zero_pop = pd.Series(
        data["S0101_C01_001E"], index=ser_ref["geographies"]["tribal"].index
    )

    df_scale.loc[ser_zero_pop.loc[ser_zero_pop != 0].index, :]

    bin_results = fit_data(
        df_fit=df_scale.loc[ser_zero_pop.loc[ser_zero_pop != 0].index, :],
        list_exceptions=exceptions[geography],
        groups=bins[geography],
        drop_na_val=True,
    )

    bin_results["bins"] = pd.DataFrame(
        bin_results["bins"], index=ser_ref["geographies"]["tribal"].index
    )

    d = {
        "ref": ref,
        "bin_meta": bin_results["meta"],
        "bin_labels": bin_results["bins"],
        "data": data,
        "indicators": df,
    }

    file_name = f'cria_{geography}_bins_{ser_ref["years"]["acs"]}'
    table_save(d, path_out / f"{file_name}.xlsx", keep_index=True)
