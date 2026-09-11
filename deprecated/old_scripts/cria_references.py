# -*- coding: utf-8 -*-
"""
Created on Mon Jun 12 09:00:00 2023

@author: jhutchison

"""

# %% Packages
""" Third party and local imports """

import pathlib
import platform
import sys

# Local Import
from utils.utils_logger import logger


# %% Functions
""" Define functions """


def get_operating_system():
    os_name = platform.system()
    return os_name


# %% Variables
""" Set script (global) variables """

# Local paths
path_data = pathlib.Path("data/")
path_out = pathlib.Path("output/")


name_top_package = "fema_cria"
name_sub_package = "fema_cria"

# Local paths
# modify path to utils and data based off cwd (run as utils or fps_server)
if pathlib.Path.cwd().stem == name_sub_package:
    path_local = pathlib.Path.cwd()

elif pathlib.Path.cwd().stem == name_top_package:
    path_local = pathlib.Path(f"{name_sub_package}/")

elif pathlib.Path.cwd().stem == "utils":
    path_local = pathlib.Path("../")

path_data = path_local / pathlib.Path("data/")
path_out = path_local / pathlib.Path("output/")
path_utils = path_local / pathlib.Path("utils/")

path_plot = path_out / pathlib.Path("plots/")

# Ensure cross-package access by modifying path
if ".." not in sys.path:
    sys.path.insert(0, "..")

# External paths
path_top = path_local.parent
path_projects = path_top.parent

os_name = get_operating_system()

# if os_name == "Windows":
#     logger.debug(f"preparing Windows path on {os_name} platform")
#     path_ext_proj = pathlib.Path(
#         "//iachs.iacc.dis.anl.gov/projects/Hurricane_Risk_Modeling/"
#     )
# elif os_name == "Linux":
#     logger.debug(f"preparing Linux path on {os_name} platform")
#     path_ext_proj = pathlib.Path(
#         "/run/user/1017/gvfs/smb-share:server=iachs.iacc.dis.anl.gov,share=projects/Hurricane_Risk_Modeling/"
#     )
# else:
#     print("unrecognized sys platform - user, update path_ext_proj")

# path_ext_grid = path_ext_proj / pathlib.Path("GIS_GRID_Data/")
# path_ext_storm = path_ext_proj / pathlib.Path("Bloemendaal/")
# path_ext_data = path_ext_proj / pathlib.Path("data/")
# path_ext_out = path_ext_proj / pathlib.Path("output/")
# path_ext_b0 = path_ext_out / pathlib.Path("blomendaal/0/")

paths = {
    "data": path_data,
    "out": path_out,
    "plot": path_plot,
    # "ext_proj": path_ext_proj,
    # "ext_grid": path_ext_grid,
    # "ext_storm": path_ext_storm,
    # "ext_data": path_ext_data,
    # "ext_out": path_ext_out,
    # "ext_b0": path_ext_b0,
}

# std_pressure = 1013.25  # (mbar)
# kts_to_mps = 0.51444444444  # mps per knt


# %% Main
""" References needs to update path to shared drive based on OS """

if __name__ == "__main__":
    os_name = get_operating_system()
    logger.info(os_name)
    logger.info(list(path_out.glob("*.pkl"))[-1])
    # logger.info(list(path_ext_data.glob("*.pkl"))[-1])
