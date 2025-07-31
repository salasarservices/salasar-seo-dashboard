# streamlit_seo_dashboard.py
# Minimalistic SEO & Reporting Dashboard with animated progress bars

import streamlit as st
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.api_core.exceptions import InvalidArgument
from google.auth.transport.requests import Request as GAuthRequest
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
import time

# =========================
# PAGE CONFIGURATION & STYLES
# =========================
st.set_page_config(
    page_title='SEO & Reporting Dashboard',
    layout='wide'
)
st.markdown(
    """
    <style>
    body {font-family: 'Arial', sans-serif; background-color: #ffffff;}
    .metric-container {padding: 1rem; background-color: #f9f9f9; border-radius: 8px;}
    .section-header {margin-top: 2rem; margin-bottom: 1rem;}
    /* Styled table */
    .styled-table {border-collapse: collapse; margin: 0; font-size: 0.9rem; width: 100%; border-radius: 5px 5px 0 0; overflow: hidden;}
    .styled-table thead tr {background-color: #2d448d; color: #ffffff; text-align: left; border-bottom: 4px solid #459fda;}
    .styled-table th, .styled-table td {padding: 12px 15px;}
    .styled-table tbody tr {border-bottom: 1px solid #dddddd;}
    .styled-table tbody tr:nth-of-type(even) {background-color: #f3f3f3;}
    .styled-table tbody tr:nth-of-type(odd) {background-color: #ffffff;}
    .styled-table tbody tr:hover {background-color: #a6ce39;}
    </style>
    """,
    unsafe_allow_html=True
)

def render_table(df):
    """
    Render a pandas DataFrame as a styled HTML table.
    """
    html = df.to_html(index=False, classes="styled-table")
    st.markdown(html, unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)

# Total Users
with col1:
    cur = get_total_users(PROPERTY_ID, sd, ed)
    prev = get_total_users(PROPERTY_ID, psd, ped)
    delta = pct_change(cur, prev)
    fill = int(max(0, min(delta, 100)))
    pb = st.progress(0)
    for i in range(fill + 1):
        pb.progress(i)
        time.sleep(0.005)
    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
    st.metric('Total Users', cur, f'{delta:.2f}%')
    st.markdown('</div>', unsafe_allow_html=True)

# Sessions
with col2:
    traf = get_traffic(PROPERTY_ID, sd, ed)
    total_sess = sum(item['sessions'] for item in traf)
    prev_sess = sum(item['sessions'] for item in get_traffic(PROPERTY_ID, psd, ped))
    delta2 = pct_change(total_sess, prev_sess)
    fill2 = int(max(0, min(delta2, 100)))
    pb2 = st.progress(0)
    for i in range(fill2 + 1):
        pb2.progress(i)
        time.sleep(0.005)
    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
    st.metric('Sessions', total_sess, f'{delta2:.2f}%')
    st.markdown('</div>', unsafe_allow_html=True)

# Organic Clicks
with col3:
    sc_rows = get_search_console(SC_SITE_URL, sd, ed)
    clicks = sum(r.get('clicks', 0) for r in sc_rows)
    prev_clicks = sum(r.get('clicks', 0) for r in get_search_console(SC_SITE_URL, psd, ped))
    delta3 = pct_change(clicks, prev_clicks)
    fill3 = int(max(0, min(delta3, 100)))
    pb3 = st.progress(0)
    for i in range(fill3 + 1):
        pb3.progress(i)
        time.sleep(0.005)
    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
    st.metric('Organic Clicks', clicks, f'{delta3:.2f}%')
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# DETAILED TABLES
# =========================
st.write('<div class="section-header"><h3>Active Users by Country (Top 5)</h3></div>', unsafe_allow_html=True)
country_df = pd.DataFrame(get_active_users_by_country(PROPERTY_ID, sd, ed))
st.table(country_df)

st.write('<div class="section-header"><h3>Traffic Acquisition by Channel</h3></div>', unsafe_allow_html=True)
st.table(pd.DataFrame(get_traffic(PROPERTY_ID, sd, ed)))

st.write('<div class="section-header"><h3>Top 10 Organic Queries</h3></div>', unsafe_allow_html=True)
sc_df = pd.DataFrame([{'page': r['keys'][0], 'query': r['keys'][1], 'clicks': r.get('clicks', 0)} for r in sc_rows])
st.dataframe(sc_df.head(10))

st.write('<div class="section-header"><h3>Page & Screen Views</h3></div>', unsafe_allow_html=True)
try:
    pv = fetch_ga4_pageviews(PROPERTY_ID, sd, ed)
    st.table(pd.DataFrame(pv))
except Exception:
    st.error('Views not available for this property')

# =========================
# FUTURE SOCIAL MEDIA ANALYTICS PLACEHOLDER
# =========================
st.write('<div class="section-header"><h2>Social Media Analytics (Coming Soon)</h2></div>', unsafe_allow_html=True)
