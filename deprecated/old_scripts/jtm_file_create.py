# -*- coding: utf-8 -*-
"""
Created on Fri Feb  4 13:57:18 2022

@author: jhutchison

mamba install xlsxwriter
mamba install openpyxl=3.1.0
"""

from utils.utils_api import geographies

import cria_pull_data as cpd
import cria_create_indicators as cci
import cria_create_aggregate_indicator as ccai


def basic():
    print("Hello, world!")

def showMyData():
    print(geographies["county"])
    #mydata = cci.create_indicators(cpd.ser_ref, geography="county")
    #print(mydata[0])
    
def createFileForTopChallenges():
    print("Creating top challenges file")
    print("Getting indicators...")
    mydata = ccai.create_agg_indicator(exceptions=ccai.exceptions, ser_ref=cpd.ser_ref, ser_data=None, geography="county", lowest_resilience=True)
    print("I'm melting!")
    mydata = mydata['scores']
    mydata = mydata.drop(columns=['NAME','state','county','county_name','state_name','state_abbr','region','name_abbr'])
    melted = mydata.melt(ignore_index=False,var_name="Indicator",value_name="value")
    print("Sorting...")
    srted = melted.sort_values(by=['GEO_ID','value'],ascending=[True,False])
    print("Dropping NaN")
    srted = srted.dropna()
    print("Ranking")
    srted['rank']=srted.groupby(['GEO_ID'])['value'].rank('first',ascending=False)
    print("Joining")
    joined = srted.join(cpd.geographies["county"])
    print("Writing...")
    joined.to_csv("data\\top_challenges.csv")
    print("Done.")

def createFileForYearToYearCorrelations():
    print("Year-To_Year Correlation...")
    
    
def createFileForRace():
    print("Race TBD")
    
def createFileForRegionalVisualizations():
    print("Creating top challenges file")
    print("Getting indicators...")
    basedata = cci.create_indicators(cpd.ser_ref, geography="county")
    popdata = basedata[1]["B02001_001E"]
    mydata = ccai.create_agg_indicator(exceptions=ccai.exceptions, ser_ref=cpd.ser_ref, ser_data=None, geography="county", lowest_resilience=True)
    print("I'm melting!")
    mydata = mydata['pos']
    #mydata = mydata['scores']
    mydata = mydata.drop(columns=['NAME','state','county','county_name','state_name','state_abbr','region','name_abbr'])
    melted = mydata.melt(ignore_index=False,var_name="Indicator",value_name="value")
    print("Joining")
    joined = melted.join(cpd.geographies["county"])
    joined = joined.join(popdata)
    
    
    print("Writing...")
    joined.to_csv("data\\basic_scores.csv")
    print("Done.")

    
if __name__ == "__main__":
    basic()
#    createFileForTopChallenges()
    createFileForRegionalVisualizations()