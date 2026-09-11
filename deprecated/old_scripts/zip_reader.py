# -*- coding: utf-8 -*-
"""
Created on Tue Feb 07 11:00:00 2023

@author: jhutchison

"""

# %% Packages
""" Third party and local imports """

import pathlib
import requests
import zipfile
import io
import pandas as pd

# %% Functions
""" Define functions """


class ZipCSVReader:
    def __init__(self, url):
        self.url = url
        self.zip_content = None

    def download_zip(self):
        """Download the zip file from the URL."""
        response = requests.get(self.url)
        response.raise_for_status()  # Raise an exception for HTTP errors
        self.zip_content = io.BytesIO(
            response.content
        )  # Store the zip content in memory

    def extract_csv(self, file_name=None):
        """Extract the CSV file from the zip content."""
        if not self.zip_content:
            raise ValueError("No zip content found. Did you call `download_zip()`?")
        with zipfile.ZipFile(self.zip_content) as zf:
            # List all files in the zip
            files = zf.namelist()
            print(f"Files in zip: {files}")

            # Choose the first file if no specific file name is given
            csv_file_name = file_name or files[0]
            if csv_file_name not in files:
                raise FileNotFoundError(f"{csv_file_name} not found in zip archive.")

            # Read the CSV content
            with zf.open(csv_file_name) as csv_file:
                return pd.read_csv(csv_file)


# %% Variables
""" Set script (global) variables """

path_data = pathlib.Path("data/")


# %% Main
""" Display task data """

if __name__ == "__main__":

    # Usage example
    url = "https://www.eac.gov/sites/default/files/2023-12/2022_EAVS_for_Public_Release_nolabel_V1.1_CSV.zip"

    reader = ZipCSVReader(url)
    reader.download_zip()

    try:
        df = reader.extract_csv()  # You can specify the CSV file name if needed
        print(df.head())
    except Exception as e:
        print(f"Error processing the file: {e}")

    print("logger update here, main complete")
