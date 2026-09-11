# -*- coding: utf-8 -*-
"""
Created on Tue Feb 25 14:50:41 2020

@author: jhutchison

"""

# %% Packages

# import json
# import logging
# import math
# import matplotlib.pyplot as plt
# import numpy as np
# import os
import pandas as pd
# import random
# import re
# import roman
# import seaborn as sns
# import sys
# import time

# from tqdm import tqdm

##############################################################################
# %% Functions


def table_save(d, file_name, keep_index=False):
    """
    Write a dictionary of dataframes to an Excel Workbook, one dataframe per
    work sheet, saved as an Excel Table.

    Parameters
    ----------
    d : Dictionary, key: sheet_name, value : df
        DESCRIPTION.

    Returns
    -------
    None.

    """
    # Create a Pandas Excel writer using XlsxWriter as the engine.
    writer = pd.ExcelWriter(file_name, engine='xlsxwriter')

    for sheet_name, df in d.items():
        df = df.copy(deep=True)
        if keep_index:  # == True:
            if pd.isna(df.index.name):  # == True:
                df.index.name = 'index'
            df.insert(loc=0, column=df.index.name, value=df.index)

        # Write the dataframe data to XlsxWriter. Turn off default header and
        # index and skip one row to allow us to insert a user defined header.
        df.to_excel(writer, sheet_name=sheet_name,
                    startrow=1, header=False, index=False)

        # Get the xlsxwriter workbook and worksheet objects.
        # workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # Get the dimensions of the dataframe.
        (max_row, max_col) = df.shape

        # Create a list of column headers, to use in add_table().
        column_settings = []
        for header in df.columns:
            column_settings.append({'header': str(header)})

        # Add the table.
        worksheet.add_table(0, 0, max_row, max_col - 1,
                            {'columns': column_settings})

        # Make the columns wider for clarity.
        worksheet.set_column(0, max_col - 1, 18)

    # Close the Pandas Excel writer and output the Excel file.
    # writer.save()
    writer.close()
    return


##############################################################################
# %% Variables
