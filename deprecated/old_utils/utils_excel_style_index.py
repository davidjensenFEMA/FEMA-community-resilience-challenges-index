# -*- coding: utf-8 -*-
"""
Created on Tue Feb 07 11:00:00 2023

@author: jhutchison
stack overflow: get-excel-style-column-names-from-column-number
https://stackoverflow.com/users/355230/martineau
https://support.microsoft.com/en-us/office/excel-specifications-and-limits-1672b34d-7043-467e-8e27-269d656771c3?ui=en-us&rs=en-us&ad=us#:~:text=Excel%20specifications%20and%20limits

"""

# %% Packages
""" Third party and local imports """

import string


# %% Functions
""" Define functions """


def excel_style_index(row, col):
    """Convert given row and column number to an Excel-style cell name."""
    global alphabet
    list_res = []
    while col:
        col, rem = divmod(col - 1, 26)
        # insert at position 0
        list_res[:0] = alphabet[rem]
    str_res = "".join(list_res)
    idx_excel = f"{str_res}{row}"
    return idx_excel


# %% Variables
""" Set local variables """

alphabet = string.ascii_uppercase


# %% Main
""" Test Excel Function """

if __name__ == "__main__":
    addresses = [
        (1, 1),
        (1, 26),
        (1, 27),
        (1, 52),
        (1, 53),
        (1, 78),
        (1, 79),
        (1, 104),
        (1, 18253),
        (1, 18278),
        (1, 702),  # -> 'ZZ1'
        (1, 703),  # -> 'AAA1'
        (1, 16384),  # -> 'XFD1'
        (1, 35277039),
    ]

    print("({:3}, {:>10}) --> {}".format("row", "col", "Excel"))
    print("==========================")
    for row, col in addresses:
        print("({:3}, {:10,}) --> {!r}".format(row, col, excel_style_index(row, col)))
