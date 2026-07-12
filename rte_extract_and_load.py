# rte_extract_and_load.py
#
# Fetches data from the RTE API (https://data.rte-france.com/), and
# loads it into a DuckDB database. 
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

import base64
import pandas as pd
from datetime import datetime, timedelta
import requests
import duckdb

from rte_get_functions import *

import os

#Configuration
client_id = os.environ.get("RTE_CLIENT_ID")
client_secret = os.environ.get("RTE_CLIENT_SECRET")
base64_creds = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

#Input Parameters
todays_date = datetime.now()
search_start_date = todays_date - timedelta(days = 7) #pd.to_datetime("2026-07-07")

database_name = "md:rte_data"

#Token & API endpoints
token_url = "https://digital.iservices.rte-france.com/token/oauth/"

#Get token
token = get_rte_token(base64_creds, token_url)

#Create/connect to database
con = duckdb.connect(database_name)

try:
    df = get_actual_generations_per_production_type(sandbox=False, token=token, start_date=search_start_date, end_date=todays_date)
    table_name = "rte_generation"
    create_or_update_table(con, table_name, df)

    # df = get_actual_generations_per_unit(sandbox=True, token=token)
    # table_name = "rte_generation_per_unit"
    # create_or_update_table(con, table_name, df)

    df = get_tempo_like_calendars(sandbox=False, token=token, start_date=search_start_date, end_date=todays_date, fallback_status="false")
    table_name = "rte_tempo"
    create_or_update_table(con, table_name, df)

    # df = get_france_power_exchanges(sandbox=False, token=token)
    # table_name = "rte_wholesale"
    # create_or_update_table(con, table_name, df)

    df = get_consumption_short_term(sandbox=False, token=token, start_date=search_start_date, end_date=todays_date)
    table_name = "rte_consumption"
    create_or_update_table(con, table_name, df)

except requests.exceptions.RequestException as e:
    print(f"An error occurred during the API request: {e}")
except KeyError as e:
    print(f"Could not parse the expected data format. Check the API documentation. Missing key: {e}")

con.close()
