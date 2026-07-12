# rte_get_functions.py
# 
# Definition of functions associated with OAuth authorization and data extraction from
# RTE APIs (https://data.rte-france.com/).
# 
# get_rte_token(base64_creds, token_url):
#   takes Base 64 coded RTE user credentials and token URL (typically "https://digital.iservices.rte-france.com/token/oauth/")
#   to return temporary access token (valid for 2 hours).
# 
# create_or_update_table(con, table_name, df):
#    Creates or updates a table table_name in a DuckDB connection con with the content in the dataframe df.
#
# get_actual_generations_per_production_type(sandbox, token, start_date, end_date):
#   Accesses the actual_generations_per_production_type resource in sandbox mode or not (boolean).
#   Retrieves hourly generation values in MW organized by production type (biomass, solar, nuclear, etc.)
#
# get_actual_generations_per_unit(sandbox, token, start_date, end_date, unit_eic_code):
#   Accesses the actual_generations_per_unit resource in sandbox mode or not (boolean).
#   Retrieves intraday generation values in MW organized by power unit (name and EIC code)
#
# get_tempo_like_calendars(sandbox, token, start_date, end_date, fallback_status):
#   Accesses the tempo_like_calendars resource in sandbox mode or not (boolean).
#   Retrieves daily EDF tempo color values (insentive system for consumer pricing)
#
# get_france_power_exchanges(sandbox, token):
#   Accesses the france_power_exchanges resource in sandbox mode or not (boolean).
#   Retrieves hourly energy prices (in €/MWh) and electricity market volume (in MW)
#
# get_consumption_short_term(sandbox, token, start_date, end_date):
#   Accesses the short_term resource in sandbox mode or not (boolean).
#   Retrieves power consumption forecast values in MW updated at 15-minute intervals by type:
#       *   Actual consumption (referred to as ACTUAL)
#       *   Intraday consumption forecast (referred to as ID)
#       *   Consumption forecast for the next day (referred to as D-1)
#       *   Consumption forecast for the day after the next day (referred to as D-2; 30-minute intervals)
# 
# Each of the API resources are limited by start_day and retrieved period durations (in days).
# Refer to official RTE API documentation for specific values, general use guidelines, and other limitations.
#
# Copyright (c) 2026 Rashid Vladimir Williams-Garcia, Atelier Markov
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import pandas as pd
from datetime import datetime
import requests
import json

todays_date = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

#Obtain temporary access token using OAuth 2.0 client credentials flow. Token is valid for 2 hours.
def get_rte_token(base64_creds, token_url):
    headers = {
        "Authorization": f"Basic {base64_creds}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        "grant_type": "client_credentials"
    }

    response = requests.post(token_url, headers=headers, data=data)
    response.raise_for_status() #raises an error for bad status codes

    return response.json()['access_token']

#Create or update DuckDB database
def create_or_update_table(con, table_name, df):
    result = con.sql(f"""
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_name = '{table_name}'
    """).fetchone()[0]

    if result>0:   #add to existing table
        df_existing = con.sql(f"SELECT * FROM {table_name}").df()

        #left join to find what's in df but not df_existing
        new_rows = df.merge(df_existing, how='left', indicator=True)
        new_rows = new_rows[new_rows['_merge'] == 'left_only'].drop('_merge', axis=1)

        con.sql(f"INSERT INTO {table_name} BY NAME SELECT * FROM new_rows")
                
        print(new_rows.head())
        print(f"Added {len(new_rows)} rows") 

    else:   #create new table
        con.sql(f"CREATE TABLE {table_name} AS SELECT * FROM df")

        print(df.head())
        print(f"Total rows: {len(df)}") 

def get_actual_generations_per_production_type(sandbox, token, start_date=todays_date, end_date=todays_date):
    print("Fetching actual generations per production type...")

    difference = end_date - start_date

    if difference.days<0:
        raise ValueError("end_date must be later than start_date")
    if difference.days>155:
        raise ValueError("Do not exceed a period of 155 days per call")
    if start_date<pd.to_datetime("2014-12-15"):
        raise ValueError("start_date must be later than 2014-12-15")

    #Once the token is obtained, API calls now use "application/json":
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    if sandbox:
        api_url = "https://digital.iservices.rte-france.com/open_api/actual_generation/v1/sandbox/actual_generations_per_production_type"
        response = requests.get(api_url, headers=headers)
    else:
        params = {
            "start_date": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_date": end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
        }

        api_url = f"https://digital.iservices.rte-france.com/open_api/actual_generation/v1/actual_generations_per_production_type"
        response = requests.get(api_url, headers=headers, params=params)

    response.raise_for_status() #raises an error for bad status codes

    full_response = response.json()
    generation_data_per_production_type = full_response['actual_generations_per_production_type']

    all_rows = []

    # Keys known from API documentation. Use value_item.get(value_item[...]) to avoid KeyError if missing
    for item in generation_data_per_production_type:
        production_type = item['production_type']
        
        for value_item in item['values']:
            all_rows.append({
                "production_type": production_type,
                "start_date": value_item['start_date'],
                "end_date": value_item['end_date'],
                "value_mw": value_item['value'],
                "updated_date": value_item.get('updated_date')
            })
   
    df = pd.DataFrame(all_rows)

    # Convert date columns to datetime
    df['start_date'] = pd.to_datetime(df['start_date'])
    df['end_date'] = pd.to_datetime(df['end_date'])
    df['updated_date'] = pd.to_datetime(df['updated_date'], errors="coerce")

    return df

def get_actual_generations_per_unit(sandbox, token, start_date=todays_date, end_date=todays_date, unit_eic_code=""):
    print("Fetching actual generations per unit...")

    difference = end_date - start_date

    if difference.days<0:
        raise ValueError("end_date must be later than start_date")
    if difference.days>7:
        raise ValueError("Do not exceed a period of 7 days per call")
    if start_date<pd.to_datetime("2011-12-13"):
        raise ValueError("start_date must be later than 2011-12-13")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    if sandbox:
        api_url = "https://digital.iservices.rte-france.com/open_api/actual_generation/v1/sandbox/actual_generations_per_unit"
        response = requests.get(api_url, headers=headers)
    else:
        params = {
            "start_date": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_date": end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "unit_eic_code" : unit_eic_code
        }

        api_url = f"https://digital.iservices.rte-france.com/open_api/actual_generation/v1/actual_generations_per_unit"#?start_date={start_date}&end_date={end_date}&unit_eic_code={unit_eic_code}"
        response = requests.get(api_url, headers=headers, params=params)

    response.raise_for_status() #raises an error for bad status codes

    full_response = response.json()
    generation_data_per_unit = full_response['actual_generations_per_unit']
    
    all_rows = []

    # Keys known from API documentation. Use value_item.get(value_item[...]) to avoid KeyError if missing
    for item in generation_data_per_unit:
        unit = item['unit']
        
        for value_item in item['values']:
            all_rows.append({
                "unit": unit,
                "start_date": value_item['start_date'],
                "end_date": value_item['end_date'],
                #"production_type": value_item['production_type'],
                "value_mw": value_item['value'],
                "updated_date": value_item.get('updated_date')  
            })
   
    df = pd.DataFrame(all_rows)

    # Convert date columns to datetime
    df['start_date'] = pd.to_datetime(df['start_date'])
    df['end_date'] = pd.to_datetime(df['end_date'])
    df['updated_date'] = pd.to_datetime(df['updated_date'], errors="coerce")

    return df

#fallback_status: boolean
def get_tempo_like_calendars(sandbox, token, start_date=todays_date, end_date=todays_date, fallback_status="false"):
    print("Fetching tempo data...")

    difference = end_date - start_date

    if difference.days<0:
        raise ValueError("end_date must be later than start_date")
    if difference.days>366:
        raise ValueError("Do not exceed a period of 366 days per call")
    if start_date<pd.to_datetime("2014-01-09"):
        raise ValueError("start_date must be later than 2014-01-09")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    if sandbox:
        api_url = "https://digital.iservices.rte-france.com/open_api/tempo_like_supply_contract/v1/sandbox/tempo_like_calendars"
        response = requests.get(api_url, headers=headers)
    else:
        params = {
            "start_date": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_date": end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "fallback_status" : fallback_status
        }

        api_url = f"https://digital.iservices.rte-france.com/open_api/tempo_like_supply_contract/v1/tempo_like_calendars"
        response = requests.get(api_url, headers=headers, params=params)

    response.raise_for_status() #raises an error for bad status codes

    full_response = response.json()
    tempo_data = full_response['tempo_like_calendars']

    # Optional: Save to JSON file
    # with open('data.json', 'w') as f:
    #     json.dump(full_response, f)    

    all_rows = []

    if sandbox:
        for data_item in tempo_data:     #sandbox version
            value_item = data_item['values']
            all_rows.append({
                "start_date": value_item['start_date'],
                "end_date": value_item['end_date'],
                "value_tempo": value_item['value'],
                "updated_date": value_item.get('updated_date')
            })
    else:
        for value_item in tempo_data['values']: #Non-sandbox version
            all_rows.append({
                "start_date": value_item['start_date'],
                "end_date": value_item['end_date'],
                "value_tempo": value_item['value'],
                "updated_date": value_item.get('updated_date')
            })
   
    df = pd.DataFrame(all_rows)

    # Convert date columns to datetime
    df['start_date'] = pd.to_datetime(df['start_date'])
    df['end_date'] = pd.to_datetime(df['end_date'])
    df['updated_date'] = pd.to_datetime(df['updated_date'], errors="coerce")

    return df

def get_france_power_exchanges(sandbox, token):
    print("Fetching hourly price and market volume data...")

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    if sandbox:
        api_url = "https://digital.iservices.rte-france.com/open_api/wholesale_market/v3/sandbox/france_power_exchanges"
        response = requests.get(api_url, headers=headers)
    else:
        api_url = f"https://digital.iservices.rte-france.com/open_api/wholesale_market/v3/france_power_exchanges"
        response = requests.get(api_url, headers=headers)

    response.raise_for_status() #raises an error for bad status codes

    full_response = response.json()
    wholesale_data = full_response['france_power_exchanges']

    #Optional: Save to JSON file
    # with open('data.json', 'w') as f:
    #     json.dump(full_response, f)    

    all_rows = []

    for item in wholesale_data:      
        for value_item in item['values']:
            all_rows.append({
                "start_date": value_item['start_date'],
                "end_date": value_item['end_date'],
                "value": value_item['value'],
                "price": value_item['price']
            })
   
    df = pd.DataFrame(all_rows)

    # Convert date columns to datetime
    df['start_date'] = pd.to_datetime(df['start_date'])
    df['end_date'] = pd.to_datetime(df['end_date'])

    return df
    
#Type: "ACTUAL", "ID", "D-1", or "D-2"
def get_consumption_short_term(sandbox, token, start_date=todays_date, end_date=todays_date):   #, type=""
    print("Fetching short-term consumption data...")

    difference = end_date - start_date

    if difference.days<0:
        raise ValueError("end_date must be later than start_date")
    if difference.days>186:
        raise ValueError("Do not exceed a period of 186 days per call")
    if start_date<pd.to_datetime("2012-12-17"):
        raise ValueError("start_date must be later than 2012-12-17")
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json"
    }

    if sandbox:
        api_url = "https://digital.iservices.rte-france.com/open_api/consumption/v1/sandbox/short_term"
        response = requests.get(api_url, headers=headers)
    else:
        params = {
            "start_date": start_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "end_date": end_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
            #"type" : type
        }

        api_url = f"https://digital.iservices.rte-france.com/open_api/consumption/v1/short_term"
        response = requests.get(api_url, headers=headers, params=params)#

    response.raise_for_status() #raises an error for bad status codes

    full_response = response.json()
    consumption_data = full_response['short_term']

    # Optional: Save to JSON file
    # with open('data.json', 'w') as f:
    #     json.dump(full_response, f)  

    all_rows = []

    for item in consumption_data:    
        type = item['type']

        for value_item in item['values']:
            all_rows.append({
                "type": type,
                "start_date": value_item['start_date'],
                "end_date": value_item['end_date'],
                "consumption_mw": value_item['value'],
                "updated_date": value_item.get('updated_date')  # .get() avoids KeyError if missing
            })
   
    df = pd.DataFrame(all_rows)

    # Convert date columns to datetime
    df['start_date'] = pd.to_datetime(df['start_date'])
    df['end_date'] = pd.to_datetime(df['end_date'])
    df['updated_date'] = pd.to_datetime(df['updated_date'], errors="coerce")

    return df
