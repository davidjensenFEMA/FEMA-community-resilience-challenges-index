# -*- coding: utf-8 -*-
"""
Created on Tue Feb 07 11:00:00 2023

@author: jhutchison

"""

# %% Packages
""" Third party and local imports """

import pandas as pd
import pathlib
import seaborn as sns


# %% Functions
""" Define functions """


# %% Variables
""" Set script (global) variables """

path_data = pathlib.Path("data/")


# %% Main
""" Display task data """

if __name__ == "__main__":

    counties = pd.read_excel(path_data / "pop_race_age.xlsx", sheet_name="Sheet2")
    count_bins = 5
    counties["size"] = pd.cut(
        counties["S0103_C01_001E"], count_bins, retbins=False, labels=range(count_bins)
    )
    counties.groupby("size")["size"].describe()

    sns.scatterplot(
        data=counties,
        x="non-white",
        y="age",
        hue="size",
        size="size",
        sizes=(20, 200),
        hue_norm=(0, 7),
        legend="full",
    )
# %%
