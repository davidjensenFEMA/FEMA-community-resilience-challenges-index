# -*- coding: utf-8 -*-
"""
Created on Tue Feb 07 11:00:00 2023

@author: jhutchison

"""

# %% Packages
""" Third party and local imports """

import pandas as pd
import pathlib

# Local
from utils.utils_excel_tools import save_excel_table


# %% Functions
""" Define functions """


# %% Variables
""" Set script (global) variables """

path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")
path_hpc = path_out / pathlib.Path("hpc/")


# %% Main
""" Display task data """

if __name__ == "__main__":

    list_factors = []

    ser_final = pd.Series(index=["bins", "meta"], dtype="object")
    for label in ["bins", "meta"]:
        ser_final[label] = pd.DataFrame()

    list_paths = list(path_hpc.glob("*.pkl"))

    for path in list_paths:
        # file_name = "impute_tract_data_match_county_2022_hpc_00.pkl"
        # ser = pd.read_pickle(path_hpc / file_name)
        ser = pd.read_pickle(path)
        label_factor = ser["bins"].columns[0]
        list_factors.append(label_factor)
        for idx_label, df in ser.items():
            print(label_factor, idx_label)
            ser_final[idx_label] = pd.concat([ser_final[idx_label], df], axis=1)

    for label in ["bins", "meta"]:
        print(ser_final[label].info())

    file_name = "cria_data_reference.xlsx"
    ref = pd.read_excel(path_data / file_name)

    print(set(ref.dropna(subset="Order_2023", axis=0)["Indicator"]) - set(list_factors))

    # Write
    d = ser_final.to_dict()

    file_name = "tract_bins_hpc"
    save_excel_table(d, path_out / f"{file_name}.xlsx", keep_index=True)
