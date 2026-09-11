# -*- coding: utf-8 -*-
"""
Created on Tue Feb 07 11:00:00 2023

@author: jhutchison

"""

# %% Packages
""" Third party and local imports """

import pathlib
import pandas as pd

# Local imports
from utils.utils_excel_tools import save_excel_table
from utils.utils_logger import logger
from cria_functions import fit_by_method


# %% Functions
""" Define functions """


# %% Variables
""" Set local variables """

file_name = "sample"

# modify path to utils and data based off cwd (run as utils or fema_cria)
if pathlib.Path.cwd().stem == "fema_cria":
    logger.debug(f"working in main, {pathlib.Path.cwd().stem}")
    path_utils = pathlib.Path("utils/")
    path_data = pathlib.Path("data/")
    path_out = pathlib.Path("output/")

elif pathlib.Path.cwd().stem == "utils":
    logger.debug(f"working in {pathlib.Path.cwd().stem}")
    path_utils = pathlib.Path.cwd()
    path_data = pathlib.Path("../data/")
    path_out = pathlib.Path("../output/")

d_ref = {}


# %% Data
""" Read local data """

xl = pd.ExcelFile(path_data / f"{file_name}.xlsx")
xl.sheet_names

dfs = {sh: xl.parse(sh) for sh in xl.sheet_names}

sheet_name = "Sheet1"
skiprows = 10

# data = dfs[sheet_name]
data = pd.read_excel(
    path_data / f"{file_name}.xlsx", sheet_name=sheet_name, skiprows=skiprows
)
data = data.dropna(axis=1, how="all")
data.columns = ["cost", "bin"]

ser_fit = fit_by_method(data.cost, groups=5)

d_df = {}
for key, val in ser_fit.items():

    if type(val) == dict:

        key_list = []
        for d_key, d_val in val.items():
            ser = pd.Series(d_val, name=d_key)
            key_list.append(ser)
        df = pd.concat(key_list, axis=1)

        d_df[key] = df.copy()

    elif type(val) == pd.core.frame.DataFrame:
        d_df[key] = val.copy()


# %% Write
""" Save to outputs """

# Excel
file_name = f"{file_name}_out"
save_excel_table(d_df, path_out / f"{file_name}.xlsx", keep_index=True)


# %% Main
""" Display task data """

if __name__ == "__main__":
    logger.info("logger update here, main complete")
