# rte_vpp_dashboard.py
# 
# Produce interactive data dashboard for a model VPP based on RTE
# wholesale price (D+1) with optimized charge/discharge cycles. 
# 
# To run: Save file and execute $ streamlit run rte_vpp_dashboard.py
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
#

import streamlit as st
import duckdb
import pandas as pd
import numpy as np
from datetime import timedelta
import plotly.express as px
from rte_vpp_optimizer import optimize_vpp

st.set_page_config(page_title="VPP Dashboard", layout="wide")

st.title("Interactive Virtual Power Plant (VPP) Dashboard")

col1, col2 = st.columns([4,1])  # 4 parts left, 1 part right
with col2:
    if st.button("Clear Cache"):
        st.cache_data.clear()
        st.rerun()

######################################################################

@st.cache_resource
def get_connection():
    return duckdb.connect('md:rte_data')
    
@st.cache_data
def load_data():
    con = get_connection()

    df = con.sql("""
          SELECT
            start_date,
            price,
            value
          FROM rte_wholesale
        """).df()
    df.set_index('start_date', inplace=True)

    return df

@st.cache_data
def filter_data(df, min_date, max_date):
    df_filtered = df[(df.index >= min_date) & (df.index <= max_date)]
    prices = df_filtered['price']

    if min_date<df.index.min():
        min_date = df.index.min()
    elif max_date>df.index.max():
        max_date = df.index.max()

    datetime_series = pd.date_range(start=min_date, end=max_date, freq='15min')
    missing_days = []
    counts = []

    if len(datetime_series)!=len(prices):
        setdiff = set(datetime_series) - set(df_filtered.index)
        missing_days = sorted({dt.strftime('%Y-%m-%d') for dt in setdiff})
        for missing_day in missing_days:
            count = sum(1 for dt in setdiff if dt.date().strftime('%Y-%m-%d') == missing_day)
            counts.append(count)

    return df_filtered, missing_days, counts

######################################################################

df = load_data()
min_date = min(df.index).to_pydatetime()
max_date = max(df.index).to_pydatetime()

st.sidebar.header("Date Range")
#st.subheader("Select Date Range")
start_date, end_date = st.sidebar.slider(
    "Select date range:",
    min_value = min_date,
    max_value = max_date + timedelta(minutes=15),
    value = (min_date, max_date),
    format = "YYYY-MM-DD HH:mm"
)

filtered_df, missing_days, counts = filter_data(df.copy(), start_date, end_date)

######################################################################

st.markdown("""
<style>
    .red-box {
        border: 3px solid #ff0000;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        background-color: rgba(255, 0, 0, 0.05);
        max-height: 150px;
        max-width: 350px;
        overflow-y: auto;    /* Enable vertical scrolling */
        overflow-x: hidden;  /* Hide horizontal scrolling */
    }
    .red-box h3 {
        color: #ff0000;
        margin-top: 0;
    }
</style>
""", unsafe_allow_html=True)

if missing_days:
    col1, col2 = st.columns([1,3])
    with col1:
        st.subheader(f"⚠️ Warning!")
    with col2:
        html_content = f"""
            <div class="red-box">
            <p>A total of <strong>{sum(counts)} missing data points</strong> have been detected for the following days :</p>
            <ul>
            """

        for i in range(len(missing_days)):
            html_content += f"""<li><strong>{missing_days[i]} :</strong> {counts[i]} missing data points</li>"""

        html_content += """</ul></div>"""
        st.markdown(html_content, unsafe_allow_html=True)

######################################################################
#################### Price visualizations ############################
######################################################################

#line chart, Wholesale Price timeseries
st.subheader("Wholesale Prices and Market Volatility")# and Market Volume
fig0 = px.line(
    filtered_df,
    x=filtered_df.index,
    y='price'
)
    
fig0.update_layout(
    xaxis_title="Date",
    xaxis=dict(showgrid=True),
    yaxis=dict(
        title="Price (€/MWh)",
    ),
)

st.plotly_chart(fig0)

#line chart, Wholesale Price timeseries
st.sidebar.header("Market Volatility Window")
window_size = st.sidebar.slider(
    "Select size of rolling window in days : ",
    min_value=0,
    max_value=int(len(filtered_df.index)/96),
    step=1,
    value=1
)

filtered_df['rolling_std'] = filtered_df['price'].rolling(window=window_size*96).std()

fig1 = px.line(
    filtered_df,
    x=filtered_df.index,
    y='rolling_std'
)
    
fig1.update_layout(
    xaxis_title="Date",
    yaxis_title="Rolling Standard Deviation (€/MWh)",
    xaxis=dict(showgrid=True)
)

st.plotly_chart(fig1)

######################################################################

# VPP parameters:
st.subheader("Virtual Power Plant Modeling")

st.sidebar.header("VPP Model Parameters")
#col1, col2 = st.sidebar.columns(2)

#with col1:
energy_capacity = st.sidebar.number_input("Energy capacity (kWh)", min_value=0, value=160, step=1)
power_max = st.sidebar.number_input("Max (dis)charge rate (kW)", min_value=0.0, value=40.0)
#with col2:
soc_initial = st.sidebar.number_input("Initial charge (kWh)", min_value=0.0, max_value=160.0, value=80.0)
efficiency = st.sidebar.number_input("Efficiency", min_value=0.0, max_value=1.0, value=0.90)

#depth of charge, fraction
soc_min, soc_max = st.sidebar.slider(
    "Depth of charge, fraction",
    min_value = 0.0,
    max_value = 1.0,
    value = (0.1, 0.9)
)

df_output = optimize_vpp(filtered_df.tail(96).copy(), energy_capacity, power_max, efficiency, soc_initial, soc_min, soc_max)

#display basic metrics
st.markdown("#### VPP Optimization Metrics")

col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Profit", f"{sum(df_output['profit']):.2f} €")
with col2:
    st.metric("Net Energy Charged", f"{np.sum(df_output['x_charge']):.2f} kWh")
with col3:
    st.metric("Net Energy Discharged", f"{np.sum(df_output['x_discharge']):.2f} kWh")

#line chart, Charge/Discharge timeseries
st.markdown("#### Charge/Discharge Recommendations")
fig2 = px.line(
    df_output,
    x=df_output.index,
    y=['x_charge', 'x_discharge']
)
    
fig2.update_layout(
    xaxis_title="Time",
    yaxis_title="Energy (kWh)"
)

st.plotly_chart(fig2)

#line chart, SoC timeseries
st.markdown("#### State-of-Charge")
fig3 = px.line(
    df_output,
    x=df_output.index,
    y='soc',
)
    
fig3.update_layout(
    xaxis_title="Time",
    yaxis_title="State-of-Charge (kWh)"
)

st.plotly_chart(fig3)

#raw data
with st.expander("View Raw Data"):
    st.dataframe(filtered_df)

#download button
csv = filtered_df.to_csv(index=False)
st.download_button(
    label="Download Data as CSV",
    data=csv,
    file_name='rte_vpp_dashboard_data.csv',
    mime='text/csv'
)
