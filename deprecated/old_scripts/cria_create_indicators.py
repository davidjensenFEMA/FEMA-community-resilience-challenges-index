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

# Local imports
from utils.utils_logger import logger

from cria_pull_data import ser_ref, pull_cria_data
from utils.utils_excel_table_save import table_save


# %% Functions
""" Define functions """


def create_indicators(ser_ref, ser_data=None, geography="county"):
    years = ser_ref["years"]
    ref = ser_ref["ref"]
    # geographies = ser_ref["geographies"]
    if ser_data is not None:
        assert ser_data.index.isin(["data"]).sum() == 1, "require data"
        data = ser_data["data"].copy(deep=True)
    else:
        data = pull_cria_data(ser_ref, geography=geography)
    labels = data.loc["labels", :]
    data = data.drop("labels", axis=0).apply(pd.to_numeric)
    """Analyze CRIA data"""
    # initialize results dataframe here
    df = pd.DataFrame(index=data.index)
    ref = ref.sort_index()
    logger.debug("sort ref, ensure enumerate " + "produces correct idx (sorted order)")
    for idx, indicator in enumerate(ref["Indicator"]):
        # break
        function = ref.loc[idx, "Function"]
        logger.info(f"{idx}: {indicator}, function: {function}")
        num = ref.loc[idx, "numerator"]
        # format numerator as list
        if type(num) == str:
            num = num.split(",")
            num = [col.strip() for col in num]
        else:
            num = [num]
        # some denomoninators are scalars (not columns)
        denom = ref.loc[idx, "denominator"]
        if function == "divide":
            if type(denom) == str:
                df[indicator] = data[num].sum(axis=1) / data[denom]
            else:
                df[indicator] = data[num].sum(axis=1) / denom
        elif function == "max":
            df[indicator] = data[num].max(axis=1) / data[denom]
        elif function == "mean":
            # in this case, need to redefine numerator
            # Pull "NETMIG{year_pop}" from numerator, unlist
            year_pop = years["pop"]
            num = [f"NETMIG{year}" for year in range(year_pop, year_pop - 5, -1)]
            df[indicator] = data[num].mean(axis=1) / data[denom]
        elif function == "divide_scalar":
            scalar = ref.loc[idx, "rate"] * 1000  # rate recorded as ~1k
            df[indicator] = data[num].sum(axis=1) / data[denom] * scalar
        elif function == "reverse_divide":
            data[f"{indicator}_num"] = pd.concat(
                [
                    pd.Series([0] * data.shape[0], index=data.index),
                    data[denom] - data[num].sum(axis=1),
                ],
                axis=1,
            ).max(axis=1)
            df[indicator] = data[f"{indicator}_num"] / data[denom]
            list_cols = [item for sublist in [num, [denom]] for item in sublist]
            df_neg = data.loc[((data[denom] - data[num].sum(axis=1)) < 0), list_cols]
            logger.info(f"reverse_divide neg values \n{df_neg}")
        else:
            logger.info(f"indicator {indicator} skipped, incorrect function")
        # always place zero where denom is zero
        if denom != 1:
            df.loc[data[denom] == 0, indicator] = 0
        df.loc[pd.isna(data[num]).sum(axis=1) > 0, indicator] = np.nan

        # if indicator == "Religion":
        #     break

    # features complete
    data = pd.concat([labels.to_frame().T, data], axis=0)
    logger.info("indicators complete")
    return df, data


# %% Variables
""" Set local variables """

path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")

# years = ser_ref["years"]
# ref = ser_ref["ref"]
geographies = ser_ref["geographies"]


# %% Main
""" Demonstrate indicators and report mean population change """

if __name__ == "__main__":

    # for geography in ["state", "county", "tract", "tribal"]:
    geography = "county"
    ser_data = None

    df, data = create_indicators(
        ser_ref=ser_ref, ser_data=ser_data, geography=geography
    )
    logger.info(f"cria indicators ready at {geography} level")
    # Excel
    d = {"cria_indicators": df, "cria_inputs": data}
    file_name = f'cria_indicators_{geography}_{ser_ref["years"]["acs"]}'
    table_save(d, path_out / f"{file_name}.xlsx", keep_index=True)
    # Pickle
    ser_data = pd.Series({"data": data, "df": df})
    ser_data.to_pickle(path_out / f"{file_name}.pkl")

    geo_ref = ser_ref["geographies"][geography]
    data = data.loc[geo_ref.index, :]
    year_netmig = ser_ref["years"]["pop"]
    years_netmig = range(int(year_netmig) - 4, int(year_netmig) + 1)
    net_mig_mean = data[[f"NETMIG{mig}" for mig in years_netmig]].mean().mean()
    logger.info(
        f"*** avg net mig from {years_netmig[0]} to {years_netmig[-1]}: "
        + f"{net_mig_mean:.2f} ***"
    )

# # %% Follow up

# df_state, data_state = create_indicators(geography="state")
# df_county, data_county = create_indicators(geography="county")

# cols_inputs = data_county.columns
# data = data_state.merge(states, left_index=True,
#                         right_on="GEO_ID",
#                         how="outer").set_index("GEO_ID")

# agg_state = data.groupby("state")[cols_inputs].\
#     agg(["mean", "sum", "count"])

# data = data_county.merge(counties, left_index=True,
#                          right_on="GEO_ID",
#                          how="outer").set_index("GEO_ID")

# agg_state_frm_county = data.groupby("state")[cols_inputs].\
#     agg(["mean", "sum", "count"])

# train_gini = pd.concat([agg_state["B19083_001E"],
#                         agg_state_frm_county["B19083_001E"]], axis=1)
# test_gini = pd.concat([df_state["GINI"],
#                        df_county["GINI"]], axis=1)
