# -*- coding: utf-8 -*-
"""
Created on Tue Feb 07 11:00:00 2023

@author: jhutchison

https://openpyxl.readthedocs.io/en/stable/tutorial.html

conda install openpyxl

"""

# %% Packages
""" Third party and local imports """

from openpyxl import Workbook, load_workbook
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils.dataframe import dataframe_to_rows

# Local import
from utils.utils_excel_style_index import excel_style_index


# %% Functions
""" Define functions """


def excel_update_workbook(file_name, ser_data, list_ignore_sheet_names=[]):

    wb = load_workbook(file_name)

    for idx_sheet, sheetname in enumerate(wb.sheetnames):
        if sheetname in list_ignore_sheet_names:
            continue
        else:
            # Clear worksheet, create a new one
            ws = wb[sheetname]
            wb.remove(ws)

            # create an empty sheet using old index
            wb.create_sheet(sheetname, idx_sheet)
            ws = wb[sheetname]

            df = ser_data[sheetname]
            df.reset_index(level=0, inplace=True)
            for row in dataframe_to_rows(df, index=False, header=True):
                ws.append(row)

            (max_row, max_col) = df.shape
            # zero index
            # shift row by 1
            # col by 0 (added/reset index in code above)
            idx_final_cell = excel_style_index(max_row + 1, max_col)

            tab = Table(displayName=f"Table{idx_sheet + 1}", ref=f"A1:{idx_final_cell}")

            # Add a default style with striped rows and banded columns
            style = TableStyleInfo(
                name="TableStyleMedium2",
                showFirstColumn=False,
                showLastColumn=False,
                showRowStripes=True,
                showColumnStripes=False,
            )
            tab.tableStyleInfo = style

            # Adjust first column width:
            new_col_length = max(len(str(cell.value)) for cell in ws["A"])
            # ws.column_dimensions[name].bestFit = True    #I tried this but the result is same
            # Added a extra bit for padding
            ws.column_dimensions["A"].width = new_col_length
            # ws.column_dimensions['A'].width = 40
            ws.add_table(tab)

    wb.save(file_name)
    return


# %% Variables
""" Set local variables """


# %% Main
""" Test Excel Function """


# %% Old Code

# # Get the dimensions of the dataframe.
# (max_row, max_col) = df.shape

# # Create a list of column headers, to use in add_table().
# column_settings = []
# for header in df.columns:
#     column_settings.append({"header": str(header)})

# # Add the table.
# worksheet.add_table(0, 0, max_row, max_col - 1, {"columns": column_settings})

# wb = Workbook()

# # grab the active worksheet
# ws = wb.active

# # Data can be assigned directly to cells
# ws["A1"] = 42

# # Rows can also be appended
# ws.append([1, 2, 3])

# # Python types will automatically be converted
# import datetime

# ws["A2"] = datetime.datetime.now()

# # Save the file
# wb.save("sample.xlsx")
