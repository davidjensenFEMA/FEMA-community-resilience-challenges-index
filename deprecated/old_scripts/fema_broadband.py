# -*- coding: utf-8 -*-
"""
Created on Fri Feb  4 13:57:18 2022

@author: jhutchison
"""

# %% Packages

# import json
import numpy as np
import pandas as pd

# import requests

# Local Import
from utils.utils_logger import logger

# from cria_pull_data import ref, geographies

from cria_functions import clean_series, fit_data
from utils.utils_excel_table_save import table_save


# %% Variables


# %% Binning support

bins = {"county": 5, "tract": 7, "tribal": 5}

issues = {"county": [], "tract": [], "tribal": []}

# jenks caspall struggles with some inputs;
# save calculation time by skipping these indicators

exceptions_d = {
    "county": {},
    "tract": {
        "bb.no.cell.perc": [
            "Fisher Jenks",
        ],
        "max.down": ["Fisher Jenks", "Jenks Caspall"],
        "median.down": ["Fisher Jenks", "Jenks Caspall"],
        "perc.above.25mbs": [
            "Fisher Jenks",
        ],
        "box.iai.value": [
            "Fisher Jenks",
        ],
        "number.providers": ["Fisher Jenks", "Jenks Caspall"],
        "cell.only.perc": [
            "Fisher Jenks",
        ],
        "ookla.median.down": [
            "Fisher Jenks",
        ],
    },
    "tribal": {},
}

# exceptions = {
#     "county": {

#     },
#     "tract": {
#         "bb.no.cell.perc": [],
#         "max.down": [],
#         "median.down": [],
#         "perc.above.25mbs": [],
#         "box.iai.value": [],
#         "number.providers": [],
#         "cell.only.perc": [],
#         "ookla.median.down": [],
#     },
#     "tribal" : {

#     }
# }

# %% Data
data = pd.read_csv(r"data\final_broadband_index_values_07152020.csv")

cols = [
    "bb.no.cell.perc",
    "max.down",
    "median.down",
    "perc.above.25mbs",
    "box.iai.value",
    "number.providers",
    "cell.only.perc",
    "ookla.median.down",
]

df = data[cols].copy(deep=True)


# %% Main
if __name__ == "__main__":
    geography = "tract"

    # df_clean = df.apply(clean_series, impute=False)

    bin_results = fit_data(
        df,
        exceptions=exceptions_d[geography],
        groups=bins[geography],
        drop_na_val=True,
        incl_natl_breaks=True,
    )

    out = {
        "bin_meta": bin_results["meta"],
        "bin_labels": bin_results["bins"],
    }
    file_name = f"data/fema_bbi_res_{geography}.xlsx"
    table_save(out, file_name, keep_index=True)


# %% Compare to last year
