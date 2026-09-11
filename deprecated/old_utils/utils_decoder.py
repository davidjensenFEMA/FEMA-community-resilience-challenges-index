# -*- coding: utf-8 -*-
"""
Created on Tue Feb 07 11:00:00 2023

@author: jhutchison

mamba install conda-forge::chardet

"""

# %% Packages
""" Third party and local imports """

import chardet
import io
import pandas as pd
import pathlib
import requests


# %% Functions
""" Define functions """


class FileDecoder:
    def __init__(self, url):
        self.url = url
        self.content = None
        self.encoding = None

    def download_file(self):
        """Download the file content from the URL."""
        response = requests.get(self.url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        self.content = response.content

    def detect_encoding(self):
        """Detect the encoding of the downloaded content."""
        if not self.content:
            raise ValueError("File content is empty. Did you call `download_file()`?")
        result = chardet.detect(self.content)
        self.encoding = result["encoding"]
        if not self.encoding:
            raise ValueError("Encoding could not be detected.")
        return self.encoding

    def get_decoded_content(self):
        """Decode the file content using the detected encoding."""
        if not self.encoding:
            raise ValueError("Encoding not detected. Call `detect_encoding()` first.")
        return self.content.decode(self.encoding)

    def to_dataframe(self, usecols=None):
        """Convert the decoded content to a pandas DataFrame."""
        decoded_content = self.get_decoded_content()
        return pd.read_csv(io.StringIO(decoded_content), usecols=usecols)


# %% Variables
""" Set script (global) variables """

path_data = pathlib.Path("data/")


# %% Main
""" Display task data """

if __name__ == "__main__":

    # Usage example
    url = "https://www.eac.gov/sites/default/files/2023-12/2022_EAVS_for_Public_Release_nolabel_V1.1_CSV.zip"
    cols_full = ["column1", "column2"]  # Replace with actual column names

    decoder = FileDecoder(url)
    decoder.download_file()
    encoding = decoder.detect_encoding()
    print(f"Detected encoding: {encoding}")

    try:
        df = decoder.to_dataframe(usecols=cols_full)
        print(df.head())
    except Exception as e:
        print(f"Error reading the file: {e}")
    print("logger update here, main complete")
