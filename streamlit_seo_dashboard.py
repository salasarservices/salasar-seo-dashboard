# streamlit_seo_dashboard.py
# Minimalistic SEO & Reporting Dashboard with animated progress bars and styled tables

import streamlit as st
import textwrap
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
    .metric-container {padding: 0.5rem 1rem 1rem 1rem; background-color: #f9f9f9; border-radius: 8px; margin-bottom: 1rem;}
    .section-header {margin-top: 2rem; margin-bottom: 1rem;}
    .styled-table {border-collapse: collapse; width: 100%; border-radius: 5px 5px 0 0; overflow: hidden;}
    .styled-table thead tr {background-color: #2d448d; color: #ffffff; text-align: left; border-bottom: 4px solid #459fda;}
    .styled-table th, .styled-table td {padding: 12px 15px;}
    .styled-table td {color: #000000 !important;}
    .styled-table tbody tr {border-bottom: 1px solid #dddddd;}
    .styled-table tbody tr:nth-of-type(even) {background-color: #f3f3f3;}
    .styled-table tbody tr:nth-of-type(odd) {background-color: #ffffff;}
    .styled-table tbody tr:hover {background-color: #a6ce39;}
    /* Metric text styling */
    .stMetricText, .stMetricValue, .stMetricLabel, .stMetricDelta {
        font-size: 32px !important;
        font-weight: bold !important;
        color: #000000 !important;
    }
    /* Progress bar spacing */
    .stProgress {
        margin: 0 !important;
        padding: 0 !important;
    }
</style>
    """,
    unsafe_allow_html=True
)

def render_table(df):
    html = df.to_html(index=False, classes='styled-table')
    st.markdown(html, unsafe_allow_html=True)

# =========================
# CONFIGURATION & AUTHENTICATION
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
    # Normalize private_key
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
# HELPER FUNCTIONS
# =========================
def pct_change(current, previous):
    if previous == 0:
        return 0
    return (current - previous) / previous * 100


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
    req = {'property': f'properties/{pid}',
           'date_ranges': [{'start_date': sd, 'end_date': ed}],
           'metrics': [{'name': 'totalUsers'}]}
    resp = ga4.run_report(request=req)
    return int(resp.rows[0].metric_values[0].value)

@st.cache_data(ttl=3600)
def get_sessions(pid, sd, ed):
    req = {'property': f'properties/{pid}',
           'date_ranges': [{'start_date': sd, 'end_date': ed}],
           'metrics': [{'name': 'sessions'}]}
    resp = ga4.run_report(request=req)
    return int(resp.rows[0].metric_values[0].value)

@st.cache_data(ttl=3600)
def get_traffic(pid, sd, ed):
    req = {
        'property': f'properties/{pid}',
        'date_ranges': [{'start_date': sd, 'end_date': ed}],
        'dimensions': [{'name': 'sessionDefaultChannelGroup'}],
        'metrics': [{'name': 'sessions'}]
    }
    resp = ga4.run_report(request=req)
    return [{'channel': row.dimension_values[0].value, 'sessions': int(row.metric_values[0].value)} for row in resp.rows]

@st.cache_data(ttl=3600)
def get_search_console(site, sd, ed, limit=10):
    body = {'startDate': sd, 'endDate': ed, 'dimensions': ['page','query'], 'rowLimit': limit}
    resp = sc.searchanalytics().query(siteUrl=site, body=body).execute()
    return resp.get('rows', [])

@st.cache_data(ttl=3600)
def get_active_users_by_country(pid, sd, ed, top_n=5):
    req = {'property': f'properties/{pid}',
           'date_ranges': [{'start_date': sd, 'end_date': ed}],
           'dimensions': [{'name': 'country'}],
           'metrics': [{'name': 'activeUsers'}],
           'order_bys': [{'metric': {'metric_name': 'activeUsers'}, 'desc': True}],
           'limit': top_n}
    resp = ga4.run_report(request=req)
    return [{'country': r.dimension_values[0].value, 'activeUsers': int(r.metric_values[0].value)} for r in resp.rows]

@st.cache_data(ttl=3600)
def fetch_ga4_pageviews(pid, sd, ed, top_n=10):
    req = {
        'property': f'properties/{pid}',
        'date_ranges': [{'start_date': sd, 'end_date': ed}],
        'dimensions': [{'name':'pageTitle'},{'name':'screenClass'}],
        'metrics':[{'name':'screenPageViews'}],
        'order_bys':[{'metric':{'metric_name':'screenPageViews'},'desc':True}],
        'limit':top_n
    }
    try:
        resp = ga4.run_report(request=req)
        return [{'pageTitle': r.dimension_values[0].value, 'screenClass': r.dimension_values[1].value, 'views': int(r.metric_values[0].value)} for r in resp.rows]
    except InvalidArgument:
        req2 = {
            'property': f'properties/{pid}',
            'date_ranges': [{'start_date': sd, 'end_date': ed}],
            'dimensions':[{'name':'pagePath'}],
            'metrics':[{'name':'screenPageViews'}],
            'order_bys':[{'metric':{'metric_name':'screenPageViews'},'desc':True}],
            'limit':top_n
        }
        resp2 = ga4.run_report(request=req2)
        return [{'pagePath': r.dimension_values[0].value, 'views': int(r.metric_values[0].value)} for r in resp2.rows]

# =========================
# SIDEBAR FILTERS
# =========================
with st.sidebar:
    st.title('Filters')
    month_sel = st.checkbox('Select Month (vs last 30 days)')
    sd, ed, psd, ped = date_ranges(month_sel)

# =========================
# METRIC CARDS
# =========================
st.write('<div class="section-header"><h2>Website Analytics</h2></div>', unsafe_allow_html=True)
col1, col2, col3 = st.columns(3)

# Total Users
with col1:
    cur = get_total_users(PROPERTY_ID, sd, ed)
    prev = get_total_users(PROPERTY_ID, psd, ped)
    delta = pct_change(cur, prev)
    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
    st.metric('Total Users', cur, f'{delta:.2f}%')
    p = max(0, min(int(delta), 100))
    bar = st.progress(0)
    for i in range(p+1):
        bar.progress(i)
    st.markdown('</div>', unsafe_allow_html=True)

# Sessions
with col2:
    cur2 = get_sessions(PROPERTY_ID, sd, ed)
    prev2 = get_sessions(PROPERTY_ID, psd, ped)
    delta2 = pct_change(cur2, prev2)
    p2 = max(0, min(int(delta2), 100))
    bar2 = st.progress(0)
    for i in range(p2+1): bar2.progress(i)
    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
    st.metric('Sessions', cur2, f'{delta2:.2f}%')
    st.markdown('</div>', unsafe_allow_html=True)

# Organic Clicks
with col3:
    cur3 = sum(r.get('clicks',0) for r in get_search_console(SC_SITE_URL, sd, ed))
    prev3 = sum(r.get('clicks',0) for r in get_search_console(SC_SITE_URL, psd, ped))
    delta3 = pct_change(cur3, prev3)
    p3 = max(0, min(int(delta3), 100))
    bar3 = st.progress(0)
    for i in range(p3+1): bar3.progress(i)
    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
    st.metric('Organic Clicks', cur3, f'{delta3:.2f}%')
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# DETAILED TABLES
# =========================

st.write('<div class="section-header"><h3>Active Users by Country (Top 5)</h3></div>', unsafe_allow_html=True)
country_df = pd.DataFrame(get_active_users_by_country(PROPERTY_ID, sd, ed))
render_table(country_df)

st.write('<div class="section-header"><h3>Traffic Acquisition by Channel</h3></div>', unsafe_allow_html=True)
traf_df = pd.DataFrame(get_traffic(PROPERTY_ID, sd, ed))
render_table(traf_df)

st.write('<div class="section-header"><h3>Top 10 Organic Queries</h3></div>', unsafe_allow_html=True)
sc_rows = get_search_console(SC_SITE_URL, sd, ed)
sc_df = pd.DataFrame([{'page':r['keys'][0],'query':r['keys'][1],'clicks':r.get('clicks',0)} for r in sc_rows])
render_table(sc_df.head(10))

st.write('<div class="section-header"><h3>Page & Screen Views</h3></div>', unsafe_allow_html=True)
try:
    pv = fetch_ga4_pageviews(PROPERTY_ID, sd, ed)
    render_table(pd.DataFrame(pv))
except Exception:
    st.error('Views not available for this property')

# Placeholder
st.write('<div class="section-header"><h2>Social Media Analytics (Coming Soon)</h2></div>', unsafe_allow_html=True)
