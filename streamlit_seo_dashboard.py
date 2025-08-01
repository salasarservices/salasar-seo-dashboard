# streamlit_seo_dashboard.py
# Minimalistic SEO & Reporting Dashboard with Styled Tables

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
# PAGE CONFIGURATION & CUSTOM STYLES
# =========================
st.set_page_config(
    page_title='SEO & Reporting Dashboard',
    layout='wide'
)

st.markdown("""
<style>
  body { font-family: Arial, sans-serif; background-color: #ffffff; }
  /* Metric styling */
  .stMetricText, .stMetricValue, .stMetricLabel, .stMetricDelta {
    font-size: 32px !important;
    font-weight: bold !important;
    color: #000000 !important;
  }
  /* Progress bar spacing */
  .stProgress { margin: 0 !important; padding: 0 !important; }
  /* Styled-table definitions for render_table output */
  table.styled-table {
    border-collapse: collapse;
    width: 100%;
    border-radius: 5px 5px 0 0;
    overflow: hidden;
    font-family: Arial, sans-serif;
  }
  table.styled-table thead tr {
    background-color: #2d448d;
    color: #ffffff;
    text-align: left;
    border-bottom: 4px solid #459fda;
  }
  table.styled-table th, table.styled-table td {
    padding: 12px 15px;
    color: #2d448d !important;
  }
  table.styled-table tbody tr:nth-of-type(even) {
    background-color: #f3f3f3;
  }
  table.styled-table tbody tr:nth-of-type(odd) {
    background-color: #ffffff;
  }
  table.styled-table tbody tr:hover {
    background-color: #a6ce39 !important;
  }
</style>
""", unsafe_allow_html=True)

# =========================
# AUTHENTICATION & CONFIG
# =========================
PROPERTY_ID = '356205245'
SC_SITE_URL = 'https://www.salasarservices.com/'
SCOPES = [
    'https://www.googleapis.com/auth/analytics.readonly',
    'https://www.googleapis.com/auth/webmasters.readonly'
]

@st.cache_resource
def get_credentials():
    sa = st.secrets['gcp']['service_account']
    info = dict(sa)
    pk = info.get('private_key', '').replace('\\n', '\n')
    if not pk.endswith('\n'):
        pk += '\n'
    info['private_key'] = pk
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(GAuthRequest())
    return creds

creds = get_credentials()
ga4 = BetaAnalyticsDataClient(credentials=creds)
sc = build('searchconsole', 'v1', credentials=creds)

# =========================
# HELPERS & DATA FETCH
# =========================
def pct_change(current, previous):
    return 0 if previous == 0 else (current - previous) / previous * 100


def date_ranges(month_sel=False):
    if month_sel:
        months, today, d = [], date.today(), date(2025,1,1)
        while d <= today:
            months.append(d)
            d += relativedelta(months=1)
        sel = st.sidebar.selectbox('Select Month', [m.strftime('%B %Y') for m in months])
        start = datetime.strptime(sel, '%B %Y').date().replace(day=1)
        end = start + relativedelta(months=1) - timedelta(days=1)
    else:
        end = date.today()
        start = end - timedelta(days=30)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - (end - start)
    fmt = lambda x: x.strftime('%Y-%m-%d')
    return fmt(start), fmt(end), fmt(prev_start), fmt(prev_end)

@st.cache_data(ttl=3600)
def get_total_users(pid, sd, ed):
    req = {'property': f'properties/{pid}', 'date_ranges': [{'start_date': sd, 'end_date': ed}], 'metrics': [{'name': 'totalUsers'}]}
    resp = ga4.run_report(request=req)
    return int(resp.rows[0].metric_values[0].value)

@st.cache_data(ttl=3600)
def get_traffic(pid, sd, ed):
    req = {'property': f'properties/{pid}', 'date_ranges': [{'start_date': sd, 'end_date': ed}], 'dimensions': [{'name': 'sessionDefaultChannelGroup'}], 'metrics': [{'name': 'sessions'}]}
    resp = ga4.run_report(request=req)
    return [{'channel': r.dimension_values[0].value, 'sessions': int(r.metric_values[0].value)} for r in resp.rows]

@st.cache_data(ttl=3600)
def get_search_console(site, sd, ed):
    body = {'startDate': sd, 'endDate': ed, 'dimensions': ['page','query'], 'rowLimit': 500}
    resp = sc.searchanalytics().query(siteUrl=site, body=body).execute()
    return resp.get('rows', [])

@st.cache_data(ttl=3600)
def get_active_users_by_country(pid, sd, ed, top_n=5):
    req = {'property': f'properties/{pid}', 'date_ranges': [{'start_date': sd, 'end_date': ed}], 'dimensions': [{'name': 'country'}], 'metrics': [{'name': 'activeUsers'}], 'order_bys': [{'metric': {'metric_name': 'activeUsers'}, 'desc': True}], 'limit': top_n}
    resp = ga4.run_report(request=req)
    return [{'country': r.dimension_values[0].value, 'activeUsers': int(r.metric_values[0].value)} for r in resp.rows]

# =========================
# RENDER TABLE UTILITY
# =========================
def render_table(df):
    html = df.to_html(index=False, classes='styled-table')
    st.markdown(html, unsafe_allow_html=True)

# =========================
# SIDEBAR FILTERS
# =========================
with st.sidebar:
    st.title('Filters')
    month_sel = st.checkbox('Select Month (vs last 30 days)')
    sd, ed, psd, ped = date_ranges(month_sel)

# =========================
# DASHBOARD LAYOUT
# =========================
st.title('SEO & Reporting Dashboard')

st.header('Website Analytics')
cur = get_total_users(PROPERTY_ID, sd, ed)
prev = get_total_users(PROPERTY_ID, psd, ped)
delta = pct_change(cur, prev)
st.metric('Total Users', cur, f"{delta:.2f}%")

traf = get_traffic(PROPERTY_ID, sd, ed)
total = sum(item['sessions'] for item in traf)
prev_total = sum(item['sessions'] for item in get_traffic(PROPERTY_ID, psd, ped))
delta2 = pct_change(total, prev_total)
st.metric('Sessions', total, f"{delta2:.2f}%")

sc_data = get_search_console(SC_SITE_URL, sd, ed)
clicks = sum(r.get('clicks',0) for r in sc_data)
prev_clicks = sum(r.get('clicks',0) for r in get_search_console(SC_SITE_URL, psd, ped))
delta3 = pct_change(clicks, prev_clicks)
st.metric('Organic Clicks', clicks, f"{delta3:.2f}%")

st.subheader('Active Users by Country (Top 5)')
styled_df = pd.DataFrame(get_active_users_by_country(PROPERTY_ID, sd, ed))
render_table(styled_df)

st.subheader('Traffic Acquisition by Channel')
styled_df2 = pd.DataFrame(get_traffic(PROPERTY_ID, sd, ed))
render_table(styled_df2)

st.subheader('Top 10 Organic Queries')
sc_df = pd.DataFrame([{'page':r['keys'][0],'query':r['keys'][1],'clicks':r.get('clicks',0)} for r in sc_data])
render_table(sc_df.head(10))

st.subheader('Page & Screen Views')
try:
    pv = fetch_ga4_pageviews(PROPERTY_ID, sd, ed)
    render_table(pd.DataFrame(pv))
except Exception:
    st.error('Views not available for this property')

st.header('Social Media Analytics (Coming Soon)')
