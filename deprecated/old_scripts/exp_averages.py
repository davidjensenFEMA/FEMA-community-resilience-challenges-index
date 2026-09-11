# -*- coding: utf-8 -*-
"""
Created on Tue Feb 07 11:00:00 2023

@author: jhutchison

"""

# %% Packages
""" Third party and local imports """

import geopandas as gdf
import pandas as pd

# Local Import
from utils.utils_logger import logger
from cria_create_aggregate_indicator import ser_ref  # , create_agg_indicator
from cria_references import paths


# %% Functions
""" Define functions """


# %% Variables
""" Set script (global) variables """

path_data = paths["data"]
path_out = paths["out"]

ref = ser_ref["ref"]
years = ser_ref["years"]
geographies = ser_ref["geographies"]


# %% Main
""" Display task data """

if __name__ == "__main__":
    geography = "county"

    # Load Data
    logger.info(f"loading {geography} data")
    if geography == "county":
        file_name = f'cria_results_{geography}_{ser_ref["years"]["acs"]}'
    elif geography == "tract":
        method = "match_county"
        file_name = f"impute_tract_data_{method}_{years['acs']}"
    ser_data = pd.read_pickle(path_out / f"{file_name}.pkl")
    logger.debug(f"\n{ser_data.index}")
    df_geo = geographies["county"].copy()
    df_geo.index.name

    file_name = f"cb_{years['acs']}_us_county_20m"
    gdf_county = gdf.read_file(path_data / f"{file_name}.zip")
    gdf_county = gdf_county.set_index("AFFGEOID")

    idx_county_out = [idx for idx in gdf_county.index if idx not in df_geo.index]
    idx_geo_out = [idx for idx in df_geo.index if idx not in gdf_county.index]


# %%
