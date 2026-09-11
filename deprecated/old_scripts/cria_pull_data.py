# -*- coding: utf-8 -*-
"""
Created on Fri Feb  4 13:57:18 2022

@author: jhutchison

mamba install xlsxwriter
mamba install openpyxl=3.1.0

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

from utils.utils_api import geographies, retrieve_data
from utils.utils_excel_table_save import table_save


logger.info(
    "issue with openpyxl as of 23 Feb 2023, force install previous version 3.1.0"
)


# %% Functions
""" Define functions """


def pull_cria_data(ser_ref, geography="county"):
    """Collect CRIA data"""
    ref = ser_ref["ref"]
    years = ser_ref["years"]
    logger.info(f"building {geography} data")
    # initialize dataframe here, to use "not in data.columns" as a check
    data = pd.DataFrame()
    # record year info in reference doc for output
    if "year" not in ref.columns:
        ref.insert(loc=list(ref.columns).index("Source") + 1, column="year", value=0)
    for idx, indicator in enumerate(ref["Indicator"]):
        logger.info(f"{idx}: {indicator}")
        # Action based on data source (ACS, CBP, etc)
        source = ref.loc[idx, "Source"]
        if source == "ACS":
            num = ref.loc[idx, "numerator"].split(",")
            # some denomoninators are scalars (not columns)
            denom = ref.loc[idx, "denominator"]
            if type(denom) == str:
                denom = denom.split(",")
            else:
                denom = [denom]
            # combine lists
            cols = [item for sublist in [num, denom] for item in sublist]
            # drop values that aren't ACS columns
            cols = [col.strip() for col in cols if len(str(col)) > 6]
            cols = [col for col in cols if col not in data.columns]
            df = retrieve_data(cols, years, source=source, geography=geography)
            ref.loc[idx, "year"] = years["acs"]
        elif source == "CBP":
            # currently, only set for one naics code per indicator
            cols = ref.loc[idx, "numerator"]
            ref.loc[idx, "year"] = float(f"{years['cbp']}.{years['naics']}")
        elif source == "EAVS":
            num = ref.loc[idx, "numerator"].split(",")
            denom = ref.loc[idx, "denominator"].split(",")
            cols = [item for sublist in [num, denom] for item in sublist]
            # ref.loc[idx, "year"] = years["eavs"]
        elif source == "ARDA":
            num = ref.loc[idx, "numerator"]
            denom = ref.loc[idx, "denominator"]
            cols = [num, denom]
        elif source == "POP":
            num = f"{ref.loc[idx, 'numerator']}{years['pop']}"
            year_pop = years["pop"]
            cols = [f"NETMIG{year}" for year in range(year_pop, year_pop - 5, -1)]
            ref.loc[idx, "year"] = year_pop
        else:
            logger.info(f"\t\t skipping {indicator}, from {source}")
            continue

        df = retrieve_data(cols, years, source=source, geography=geography)

        if idx == 0:
            data = df[cols].copy(deep=True)
            data.index = df.index
            logger.debug(data.shape)
        else:
            data = data.merge(df[cols], left_index=True, right_index=True, how="outer")
            logger.debug(f"joining {df.shape} to {data.shape}")
    # Completed all cria data features
    # if geography != "state":
    # data_states = data.loc[data.index.str[-3:] == "000", :]
    # logger.debug(f"dropping {data_states.shape[0]} state rows")
    # data = data.drop(data_states.index, axis=0)
    idx_issues = pd.isna(data.index)
    logger.debug(f"dropping {sum(idx_issues)} {geography} rows")
    data = data.loc[~idx_issues, :].copy()
    logger.info(
        f"data pull complete for {geography}, " f"final inputs shape {data.shape}"
    )
    # final step, fillna with zeros in cbp rows
    cols_cbp = ref.loc[ref["Source"] == "CBP", "numerator"]
    idx_cbp = data[cols_cbp].apply(pd.isna)
    logger.info(f"filling {idx_cbp.sum(axis=0).sum()} " "cbp empty values with zeros")
    data[cols_cbp] = data[cols_cbp].fillna(0)

    # Puerto Rico Limited English
    # Exclude tribal (no PR)
    if geography in ["state", "county", "tract"]:
        geo_ref = geographies[geography]
        idx_PR = geo_ref.loc[geo_ref["state"] == 72, :].index
        logger.info(f"removing {len(idx_PR)} Lim Eng rows from Puerto Rico data")
        col_LE = ref.loc[ref["Indicator"] == "Limited English", "numerator"]
        data.loc[idx_PR, col_LE] = np.array([np.nan] * len(idx_PR)).reshape(-1, 1)
    return data


# %% Variables
""" Set local variables """

path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")


# %% CRIA reference file
""" Read CRIA reference """

d_ref = {}

file_name = "cria_data_reference.xlsx"
xl = pd.ExcelFile(path_data / file_name)
xl.sheet_names

dfs = {sh: xl.parse(sh) for sh in xl.sheet_names}
# years = {"acs": 2021, "cbp": 2020, "naics": 2017, "pop": 2020, "acs_labels": 2020}
years = {key: val for key, val in zip(dfs["Years"].label, dfs["Years"].year_ref)}

ref = dfs["Status"]
# ref = pd.read_excel(path_data / file_name, sheet_name="Status")
label_reference = "Order_2023"
ref = ref.dropna(subset=[label_reference], axis=0)
ref = ref.sort_values(label_reference)

idx_religion = (
    ref.where(ref["Indicator"] == "Religion").dropna(axis=0, how="all").index[0]
)
ref.loc[idx_religion, "denominator"] = (
    f"{ref.loc[idx_religion, 'denominator']}{years['asarb']}"
)


# %% Prep output
""" Labeled array, d_ref """
d_ref["ref"] = ref
d_ref["years"] = years
d_ref["geographies"] = geographies

ser_ref = pd.Series(d_ref)


# %% Main
""" Demonstrate data retrieval """

if __name__ == "__main__":
    # S1701_C02_001E	S1701_C01_001E
    geography = "county"
    data = pull_cria_data(ser_ref, geography)
    logger.info(f"cria data ready at {geography} level")
    ser = data.loc["labels", :].copy(deep=True)
    data = data.drop("labels").apply(pd.to_numeric)
    data = pd.concat([ser.to_frame().T, data], axis=0)
    # Excel
    d = {"cria_inputs": data}
    file_name = f"cria_inputs_{geography}"
    table_save(d, path_out / f"{file_name}.xlsx", keep_index=True)
