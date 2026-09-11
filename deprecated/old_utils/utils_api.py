# -*- coding: utf-8 -*-

"""
Created on Fri Feb  4 10:58:24 2022

@author: johnk

https://docs.python-requests.org/en/latest/
"""


# %% Packages
""" Third party and local imports """

import io
import json
import logging

import numpy as np
import pandas as pd
from pathlib import Path
import re
import requests
import sys

from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry


# Local Import
from utils_logger import LoggerSetup

# Initialize logger
logger = LoggerSetup.setup_logger("api", Path("logs"), logging.DEBUG)
logger.info("Logger initialized for Utils API module")


# %% Functions
""" Define functions """


def create_geoid(state, county):
    """Build GEOID in similar to 0500000US01001 from State and County"""
    assert type(state) == pd.Series, "input state as series"
    assert type(county) == pd.Series, "input county as series"
    state = state.copy().astype(str).str.pad(2, fillchar="0")
    county = county.copy().astype(str).str.pad(3, fillchar="0")
    geoid = "0500000US" + state + county
    return geoid


def create_acs_api(cols, geography="county", year_acs=2020, full_table=False):
    """Build API link based on column information from a list of columns"""
    global list_state_codes_padded
    assert type(cols) == list, "input cols as list"
    # Base/static information
    lnk_census_data_api = "https://api.census.gov/data/"
    lnk_key = "&key=d665833afd3f36d12b9a0e2832c3d6b92830a29a"
    lnk_dataset = f"{year_acs}/acs/acs5/"
    # Split use case where we want the full table
    # Determines variable list structure
    if full_table:
        id_table = cols[0]
        lnk_variable_list = f"group({id_table})"
    else:
        id_table = cols[0].split("_")[0]
        cols_str = ",".join(cols)
        lnk_variable_list = "NAME,GEO_ID," + cols_str
    # Identify table
    if id_table[0] == "B":
        # modify data set link:
        lnk_dataset = f"{year_acs}/acs/acs5"
        # detailed table
        lnk_get_fnc = "?get="
    elif id_table[0] == "S":
        # subject table
        lnk_get_fnc = "subject?get="
    elif id_table[:2] == "DP":
        # data profile
        lnk_get_fnc = "profile?get="
    elif id_table[:2] == "CP":
        # comparison profile
        lnk_get_fnc = "cprofile?get="
    lnk_predicate = "&for="
    if geography == "county":
        lnk_geography = "county:*&in=state:*"
    elif (geography == "tract") or (geography == "census"):
        lnk_geography = f"tract:*&in=state:{list_state_codes_padded}&in=county*"
    elif geography == "tribal" or geography == "tribal_tract":
        # lnk_geography = r"tribal%20census%20tract"
        lnk_geography = (
            r"american%20indian%20area/alaska%20native%20area/hawaiian%20home%20land:*"
        )
        if geography == "tribal_tract":
            lnk_tract = r"tribal%20census%20tract"
            lnk_geography = f"{lnk_tract}:*&in={lnk_geography}"
    # ex: https://api.census.gov/data/2022/acs/acs5?get=NAME,B01001_001E&for=tribal%20census%20tract:*&in=american%20indian%20area/alaska%20native%20area/hawaiian%20home%20land:3000
    elif geography == "state":
        lnk_geography = r"state:*"
    else:
        logger.debug("unacceptable geography, can't build link")
        sys.exit()
    link = (
        f"{lnk_census_data_api}{lnk_dataset}{lnk_get_fnc}"
        + f"{lnk_variable_list}{lnk_predicate}{lnk_geography}{lnk_key}"
    )
    return link


def create_cbp_api(code, years):
    """Build API link based on column information from a list of NAICs codes"""
    assert type(code) == int, "input naics codes as int, *not* list"
    year_cbp = years["cbp"]
    year_naics = years["naics"]
    # Base/static information
    lnk_census_data_api = "https://api.census.gov/data/"
    lnk_key = "&key=d665833afd3f36d12b9a0e2832c3d6b92830a29a"
    # Action based on CBP vs ACS:
    logger.debug(
        "cbp year and naics codes are separate values, "
        + "https://www.census.gov/naics/"
    )
    lnk_dataset = f"{year_cbp}/cbp"
    lnk_get_fnc = "?get="
    lnk_variable_list = f"NAME,GEO_ID,NAICS{year_naics}_LABEL,ESTAB"
    lnk_predicate = "&for="
    lnk_geography = "county:*&in=state:*"
    lnk_naics = f"&NAICS{year_naics}={code}"
    link = (
        f"{lnk_census_data_api}{lnk_dataset}{lnk_get_fnc}"
        + f"{lnk_variable_list}{lnk_predicate}"
        + f"{lnk_geography}{lnk_naics}{lnk_key}"
    )
    return link


def label_data(data, cols, years, df_labels, source="ACS", geography="county"):
    cols_geo = {
        "tract": ["tract", "county", "state"],
        "county": ["county", "county"],
        "state": ["state"],
        "tribal": [],
    }
    year_naics = years["naics"]
    if source == "ACS":
        data.loc["labels", cols] = df_labels.loc[cols, "label"]
        data = data.drop(cols_geo[geography], axis=1)
    elif source == "CBP":
        data.loc["labels", "ESTAB"] = data[f"NAICS{year_naics}_LABEL"].unique()[0]
        data = data.rename(
            {"ESTAB": int(data[f"NAICS{year_naics}"].unique()[0])}, axis=1
        )
        data = data.drop([f"NAICS{year_naics}_LABEL", f"NAICS{year_naics}"], axis=1)
        data = data.drop(["state", "county"], axis=1)
    elif source == "POP":
        data = data.drop(["STATE", "COUNTY"], axis=1)
        for col in data.columns:
            year_pop = int(col[-4:])
            data.loc["labels", col] = (
                f"Net migration in period 7/1/{year_pop-1} to 6/30/{year_pop}"
            )
            data.loc["labels", col] = (
                f"Net migration in period 7/1/{year_pop-1} to 6/30/{year_pop}"
            )
    elif source == "EAVS":
        data = data[["A1a", "A1c"]].copy()
        data.loc["labels", ["A1a", "A1c"]] = ["A1a Total Reg", "A1c Total Inactive"]
    elif source == "ARDA":
        data = data[cols].copy(deep=True)
        data.loc["labels", ["TOTADH", "POP2010"]] = [
            "All denominations/groups--Total number of adherents (2010)",
            "Population in 2010",
        ]
    return data


def retrieve_data(cols, years, source="ACS", geography="county"):
    """Create link and retrieve data"""
    global counties
    # Build API based on remote json or csv:
    # JSON:
    if (source == "ACS") or (source == "CBP"):
        # Distinct link builds based on source type (ACS/CBP)
        if source == "ACS":
            cols_full = cols[:]
            link = create_acs_api(cols_full, geography=geography, year_acs=years["acs"])
        elif source == "CBP":
            # cols is an int, must remain int for cpb_api
            cols_full = [cols]
            link = create_cbp_api(cols, years=years)
        session = requests.Session()
        retry = Retry(connect=3, backoff_factor=0.5)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)

        # session.get(link)
        res = session.get(link)
        # res = requests.get(link)
        response = json.loads(res.text)
        data = pd.DataFrame(data=response[1:], columns=response[0])
        # Clarify missing ACS data:
        if source == "ACS":
            for col in data[cols_full]:
                data.loc[data[col].astype(float) == -666666666.0, col] = np.nan

    elif source == "EAVS":
        cols_eavs = cols[:]
        cols_geo = ["FIPSCode", "Jurisdiction_Name", "State_Abbr"]
        cols_full = [item for sublist in [cols_geo, cols_eavs] for item in sublist]
        # cols = ["FIPSCode", "Jurisdiction_Name", "State_Abbr", "A1a", "A1c"]
        # link_voter = (
        #     "https://www.eac.gov/sites/default/files/EAVS%202020/"
        #     + "2020_EAVS_for_Public_Release_nolabel_V2.csv"
        # )

        ## year 2024

        # link_voter = "https://www.eac.gov/sites/default/files/EAVS%202020/"
        # link_voter += "2020_EAVS_for_Public_Release_nolabel_V2.csv"
        # res = requests.get(link_voter)
        # # Confirmed datatype with chardetect
        # # chardet.detect(res.content)
        # data = pd.read_csv(io.StringIO(res.content.decode("utf-8")), usecols=cols_full)

        # year 2025
        url = "https://www.eac.gov/sites/default/files/2023-12/2022_EAVS_for_Public_Release_nolabel_V1.1_CSV.zip"

        reader = ZipCSVReader(url)
        reader.download_zip()

        try:
            data = reader.extract_csv()  # You can specify the CSV file name if needed
            print(data.head())
        except Exception as e:
            print(f"Error processing the file: {e}")

        logger.debug(
            "supplied FIPS codes do not align well to unsupervised"
            + "merging, generate matching fields by county, state; "
            + "merge with ACS GEO_IDs"
        )
        data["Jurisdiction_Name"] = data["Jurisdiction_Name"].str.lower().str.strip()
        data["State_Abbr"] = data["State_Abbr"].str.lower().str.strip()
        data["name_abbr"] = data["Jurisdiction_Name"] + ", " + data["State_Abbr"]
        counties["name_abbr"] = (
            counties["county_name"].str.lower().str.strip()
            + ", "
            + counties["state_abbr"].str.lower().str.strip()
        )
        data = data.merge(
            counties[["name_abbr"]].reset_index(), on="name_abbr", how="outer"
        )
        logger.debug(
            "several counties not available - but component "
            + "towns/villages are available (aggregate)"
        )
        logger.debug("two missing type values")
        logger.debug("RespondedDoesNotApply (-88)	RespondedDataNotAvailable (-99)")
        logger.debug("if 'data does not apply' treat value as 0?")
        logger.debug("if 'data not available' treat as missing")
        eavs_issues = {
            -88: 0,  # RespondedDoesNotApply
            -99: np.nan,  # RespondedDataNotAvailable
        }
        data = data.replace(eavs_issues)

    elif source == "ARDA":
        if years["asarb"] == 2010:
            logger.info(f"running 2010 arda data")
            data = arda.copy(deep=True)
            data["GEO_ID"] = create_geoid(data["STCODE"], data["CNTYCODE"])
            cols_full = cols[:]
        elif years["asarb"] == 2020:
            data = asarb.copy(deep=True).dropna(axis=0, subset=["STATE NAME"])
            logger.info(f"running asarb data")
            # match column labels with arda data
            data["STCODE"] = data["FIPS"].astype(str).str[:2]
            data["CNTYCODE"] = data["FIPS"].astype(str).str[2:]
            data["GEO_ID"] = create_geoid(data["STCODE"], data["CNTYCODE"])
            data = data.rename(
                {"TOTAL POPULATION": "POP2020", "ADHERENTS": "TOTADH"}, axis=1
            )
            cols_full = cols[:]
        else:
            logger.info("years out of bounds on asarb/arda data")
            return

    elif source == "POP":
        cols_years = cols[:]
        cols_geo = ["STATE", "COUNTY"]
        cols_full = [item for sublist in [cols_years, cols_geo] for item in sublist]
        year_pop = years["pop"]
        file_name = f"co-est{year_pop}-alldata.csv"
        # old range, decade no longer inclusive of current data
        year_remainder = year_pop % 10
        if year_remainder == 0:
            year_remainder = 10
        year_base = year_pop - (year_remainder)
        year_range = f"{year_base}-{year_pop}"
        link_popchange = "https://www2.census.gov/programs-surveys/popest/"
        link_popchange += f"datasets/{year_range}/counties/totals/"
        link_popchange += file_name
        years_request = [int(year[-4:]) for year in cols_years]
        years_avail = list(range(year_base, year_pop + 1))
        res = requests.get(link_popchange)
        if set(years_request).issubset(years_avail):
            # Confirmed datatype with chardetect
            # chardet.detect(res.content)
            data = pd.read_csv(
                io.StringIO(res.content.decode("ISO-8859-1")), usecols=cols_full
            )
        else:
            # requires two tables, two requests
            cols_request = [f"NETMIG{year}" for year in years_avail]
            cols_req_full = [
                item for sublist in [cols_request, cols_geo] for item in sublist
            ]
            data = pd.read_csv(
                io.StringIO(res.content.decode("ISO-8859-1")), usecols=cols_req_full
            )

            # get the remaining cols
            years_remaining = list(set(years_request) - set(years_avail))
            link_popchange2 = "https://www2.census.gov/programs-surveys/popest/"
            link_popchange2 += "datasets/2010-2020/counties/totals/"
            link_popchange2 += f"co-est2020-alldata.csv"
            res = requests.get(link_popchange2)
            cols_request2 = [f"NETMIG{year}" for year in years_remaining]
            cols_req_full2 = [
                item for sublist in [cols_request2, cols_geo] for item in sublist
            ]

            data2 = pd.read_csv(
                io.StringIO(res.content.decode("ISO-8859-1")), usecols=cols_req_full2
            )
            data = data.merge(data2, left_on=cols_geo, right_on=cols_geo)

        data["GEO_ID"] = create_geoid(data["STATE"], data["COUNTY"])
    data = data.set_index("GEO_ID", drop=True).sort_index()
    data = label_data(data, cols_full, years, df_labels, source, geography)
    return data


# %% Variables
""" Set local variables """

# logger = logging.getLogger("cria_logger")

# modify path to utils and data based off cwd (run as utils or fema_cria)
if Path.cwd().stem == "fema_cria":
    logger.debug(f"working in main, {Path.cwd().stem}")
    path_utils = Path("utils/")
    path_data = Path("data/")
    path_out = Path("output/")

elif Path.cwd().stem == "utils":
    logger.debug(f"working in {Path.cwd().stem}")
    path_utils = Path.cwd()
    path_data = Path("../data/")
    path_out = Path("../output/")

# years = {"acs": 2021, "cbp": 2020, "naics": 2017, "pop": 2020, "acs_labels": 2020}
file_name = "cria_data_reference.xlsx"
xl = pd.ExcelFile(path_data / file_name)
xl.sheet_names

dfs = {sh: xl.parse(sh) for sh in xl.sheet_names}
# years = {"acs": 2021, "cbp": 2020, "naics": 2017, "pop": 2020, "acs_labels": 2020}
years = {key: val for key, val in zip(dfs["Years"].label, dfs["Years"].year_ref)}


# Alternative, change wd (phased out)
# if Path.cwd().stem != "fema_cria":
#     import os
#     os.chdir(r"..")
#     logger.info(f"changing directory to {os.getcwd()}")

# Links to data hosts

# Census: "https://www.census.gov/data/developers/data-sets.html"
# ACS: "https://www.census.gov/data/developers/data-sets/acs-5year.html"

# CBP: r"https://www.census.gov/data/developers/data-sets/" + \
#     "cbp-nonemp-zbp/cbp-api.html"

# ARDA
# working for 2010
file_name = "U.S. Religion Census Religious Congregations "
file_name += "and Membership Study, 2010 (County File).XLSX"
arda = pd.read_excel(path_data / file_name)

# working for 2020
link_asarb = "https://www.usreligioncensus.org/sites/default/files/"
link_asarb += "2022-11/2020%20USRC%20Summaries.xlsx"

try:
    xls = pd.ExcelFile(link_asarb)
    asarb = pd.read_excel(xls, sheet_name="2020 County Summary")
except:
    file_name = "2020 USRC Summaries"
    pd.read_excel(path_data / f"{file_name}.xlsx", sheet_name="2020 County Summary")

# # not working for 2010
# link_arda = "https://osf.io/gph53/download"
# data = pd.read_excel(link_arda)


# %% Labels
""" Collect census variable information """

res_list = []
table_types = ["", "subject/", "profile/", "cprofile/"]
for table_type in table_types:
    link = (
        f"https://api.census.gov/data/{years['acs_labels']}/acs/acs5/"
        + table_type
        + "variables.json"
    )
    session = requests.Session()
    retry = Retry(connect=3, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)

    # session.get(link)
    res = session.get(link)
    # res = requests.get(link)
    response = json.loads(res.text)
    response = response["variables"]
    res_list.append(pd.DataFrame.from_dict(response).T)

df_labels = pd.concat(res_list, axis=0)


# %% GEO_ID references
""" Collect geography data by level from census """

geographies = {}

cols_geo = {
    "tract": ["tract_name", "county_name", "state_name"],
    "county": ["county_name", "state_name"],
}

regions = pd.read_excel(
    path_utils / "states_and_regions.xlsx", sheet_name="states_and_regions"
)

regions = regions.dropna(axis=0, how="any")

regions = regions.set_index("GEO_ID").sort_index()

list_state_codes = regions["state"].copy().dropna().astype(int)
list_state_codes = list_state_codes.astype(str).str.pad(2, fillchar="0")
list_state_codes = list_state_codes.to_list()
list_state_codes_padded = re.sub(r"[\[\]\'\s]", "", str(list_state_codes))


# list_geographies = ["state", "county", "tract", "tribal", "tribal_tract"]
list_geographies = ["state", "county", "tract", "tribal"]
# list_geographies = ["county"]
logger.info("*** problem here, update year by acs update ***")
for geography in list_geographies:
    cols = ["B01001_001E"]
    link = create_acs_api(cols, geography=geography, year_acs=2022)
    res = requests.get(link)
    response = json.loads(res.text)
    df_geo = pd.DataFrame(data=response[1:], columns=response[0])

    if geography == "state":
        df_geo["state"] = df_geo["state"].astype(float)
        df_geo = df_geo.merge(
            regions[["state", "state_abbr", "region"]],
            left_on=df_geo["state"],
            right_on=regions["state"],
            how="left",
            suffixes=(None, "_y"),
        )

    elif geography in ["county", "tract"]:
        states = geographies["state"]
        df_geo["state"] = df_geo["state"].astype(float)
        if geography == "county":
            df_geo[cols_geo[geography]] = df_geo["NAME"].str.split(", ", expand=True)
        else:
            df_geo[cols_geo[geography]] = df_geo["NAME"].str.split("; ", expand=True)
        df_geo = df_geo.merge(
            states[["state", "state_abbr", "region"]],
            left_on=df_geo["state"],
            right_on=states["state"],
            how="left",
            suffixes=(None, "_y"),
        )

    if geography != "tribal":
        df_geo = df_geo.drop(["key_0", "state_y", "B01001_001E"], axis=1)

    df_geo = df_geo.set_index("GEO_ID").sort_index()
    geographies[geography] = df_geo.copy()
    logger.info(f"{geography} geo data ready")

states = geographies["state"]
counties = geographies["county"]

ser_geo = pd.Series(geographies)
ser_geo.to_pickle(path_data / "ser_geo.pkl")

# cols = ["B01001_001E"]
# link = create_acs_api(cols, geography="tract")
# res = requests.get(link)
# response = json.loads(res.text)
# tracts = pd.DataFrame(data=response[1:], columns=response[0])
# tracts["state"] = tracts["state"].astype("float")
# tracts[["tract_name", "county_name", "state_name"]] = tracts["NAME"].str.split(
#     ", ", expand=True
# )
# tracts = tracts.merge(
#     states[["state", "state_abbr", "region"]],
#     left_on=tracts["state"],
#     right_on=states["state"],
#     how="left",
#     suffixes=(None, "_y"),
# )
# tracts = tracts.drop(["key_0", "state_y"], axis=1)
# tracts = tracts.set_index("GEO_ID").sort_index()

# cols = ["B01001_001E"]
# link = create_acs_api(cols, geography="tribal")
# res = requests.get(link)
# response = json.loads(res.text)
# tribes = pd.DataFrame(data=response[1:], columns=response[0])
# tribes = tribes.set_index("GEO_ID").sort_index()

# geographies = {
#     "state": states,
#     "county": counties,
#     "tract": tracts,
#     "tribal": tribes,
#     "tract_codes": tract_codes,
# }

# counties = pd.read_excel(path_utils / "info_counties.xlsx")
# counties[["county_name", "state_name"]] = counties["NAME"].str.split(", ", expand=True)
# counties = counties.merge(
#     states[["state", "state_abbr", "region"]],
#     left_on=counties["state"],
#     right_on=states["state"],
#     how="left",
#     suffixes=(None, "_y"),
# )
# counties = counties.drop(["key_0", "state_y"], axis=1)
# counties = counties.set_index("GEO_ID").sort_index()
# counties.info()

# tracts = pd.read_excel(path_utils / "info_tracts.xlsx")
# tracts[["tract_name", "county_name", "state_name"]] = tracts["NAME"].str.split(
#     ", ", expand=True
# )
# tracts = tracts.merge(
#     states[["state", "state_abbr", "region"]],
#     left_on=tracts["state"],
#     right_on=states["state"],
#     how="left",
#     suffixes=(None, "_y"),
# )
# tracts = tracts.drop(["key_0", "state_y"], axis=1)
# tracts = tracts.set_index("GEO_ID").sort_index()
# tracts.info()

# link_tract_codes = "https://www2.census.gov/geo/docs/maps-data/"
# link_tract_codes += "data/rel2020/tract/tab20_tract20_tract10_natl.txt"

# res = requests.get(link_tract_codes)

# tract_codes = pd.read_csv(
#     io.StringIO(res.content.decode("utf-8")),
#     delimiter="|",
# )


# %% Main
""" Demonstrate link creation and data retrieval """

if __name__ == "__main__":
    data = pd.DataFrame()
    cols = ["B09005_004E", "B09005_005E"]
    # geography = "tribal_tract"
    geography = "county"
    logger.debug(create_acs_api(cols, geography=geography))
    df = retrieve_data(cols, years, source="ACS", geography=geography)
    data = pd.concat([data, df[cols]], axis=1)
    logger.debug(f"data shape: {data.shape}")


# %% Notes
""" Notes """

# url = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=CHXRSA'
# r = requests.get(url)
# open('temp.csv', 'wb').write(r.content)
# df = pd.read_csv('temp.csv')
