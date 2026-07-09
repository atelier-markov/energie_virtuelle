# rte_generation_dashboard.py
# 
# Produces interactive data dashboard with bar chart, line chart, and area chart.
# 
# To run: Save file and execute $ streamlit run rte_generation_dashboard.py
#
# Copyright (c) 2026 Rashid Vladimir Williams-Garcia, Atelier Markov
# Licensed under the MIT License
#

import duckdb
import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Power Generation Dashboard", layout="wide")

@st.cache_data  #to prevent reloading data on every interaction

def load_data():
    con = duckdb.connect('rte_data.duckdb')

    df = con.sql("""
            SELECT 
                production_type,
                CAST(start_date AS DATE) AS date,
                SUM(value_mw) AS total_generation
            FROM rte_generation
            WHERE production_type != 'TOTAL'
            GROUP BY
                production_type,
                CAST(start_date AS DATE)
            ORDER BY date, production_type
        """).df()
    return df

df = load_data()

st.title("Interactive RTE Actual Generation Dashboard")
st.sidebar.header("Filters")

#date range filter
min_date = df['date'].min()
max_date = df['date'].max()
date_range = st.sidebar.date_input(
    "Select Date Range",
    value = (min_date, max_date),
    min_value = min_date,
    max_value = max_date
)

#type filter
types = st.sidebar.multiselect(
    "Select Types",
    options = df['production_type'].unique(),
    default = df['production_type'].unique()
) 

#apply filters
filtered_df = df[
    (df['date'] >= pd.to_datetime(date_range[0])) &
    (df['date'] <= pd.to_datetime(date_range[1])) &
    (df['production_type'].isin(types))
]

#display basic metrics
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Generation", f"{filtered_df['total_generation'].sum():,.0f} MW")
with col2:
    st.metric("Number of Production Types", len(filtered_df['production_type'].unique()))
with col3:
    st.metric("Date Range", f"{filtered_df['date'].min().date()} to {filtered_df['date'].max().date()}")

# Main visualizations
col1, col2 = st.columns(2)

#bar chart, generation by type
with col1:
    st.subheader("Total Generation by Type")
    fig1 = px.bar(
        filtered_df.groupby('production_type')['total_generation'].sum().reset_index(),
        x='production_type',
        y='total_generation',
        color='production_type',
        #title="Total Generation by Type"
    )

    fig1.update_layout(
        xaxis_title="",
        yaxis_title="Total Generation (MW)",
        legend_title="Production Type"
    )

    st.plotly_chart(fig1, use_container_width=True)

#line chart, generation timeseries
with col2:
    st.subheader("Total Generation Over Time")
    fig2 = px.line(
        filtered_df.groupby('date')['total_generation'].sum().reset_index(),
        x='date',
        y='total_generation',
        #title="Total Generation Over Time"
    )
    
    fig2.update_layout(
        xaxis_title="Date",
        yaxis_title="Total Generation (MW)"
    )

    st.plotly_chart(fig2, use_container_width=True)

#stacked area chart
st.subheader("Stacked Area Chart: Total Generation Over Time by Type")

fig3 = px.area(
    filtered_df,
    x='date',
    y='total_generation',
    color='production_type',
    #title="Stacked Area Chart - Total Value by Type",
    labels={
        'date': 'Date',
        'total_generation': 'Total Generation (MW)',
        'production_type': 'Type'
    },
    color_discrete_sequence=px.colors.qualitative.Set1
)

fig3.update_layout(
    xaxis_title="Date",
    yaxis_title="Total  Generation (MW)",
    hovermode='x unified',
    legend_title="Production Type",
    template='plotly_white'
)

st.plotly_chart(fig3, use_container_width=True)

#raw data
with st.expander("View Raw Data"):
    st.dataframe(filtered_df)

#download button
csv = filtered_df.to_csv(index=False)
st.download_button(
    label="Download Data as CSV",
    data=csv,
    file_name='rte_generation_dashboard_data.csv',
    mime='text/csv'
)