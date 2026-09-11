# -*- coding: utf-8 -*-
"""
Created on Mon Dec 20 11:20:55 2021

@author: jhutchison

unicode error in read_csv
attempt to detect the encoding

then
read as rb, convert to str, then to pandas
"""

# %% Imports
import chardet
import pandas as pd

from io import StringIO

# %% Variables
# Variables
file_name = 'text.csv'


# %% Character Detect
with open(file_name, "rb") as f:
    print(chardet.detect(f.read()))


# %% Open and convert
with open(file_name, "rb") as f:
    contents = f.read()
s = str(contents, 'utf-8')
file = StringIO(s)
file = pd.read_csv(file)
