# streamlit_seo_dashboard.py
# Minimalistic SEO & Reporting Dashboard with clean, wide layout

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
    body {font-family: 'Arial', sans-serif;}
    .metric-container {padding: 1rem; background-color: #f9f9f9; border-radius: 8px;}
    .section-header {margin-top: 2rem; margin-bottom: 1rem;}
    </style>
    """,
    unsafe_allow_html=True
)

# =========================
# CONFIGURATION & AUTH
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
# HELPERS
# =========================
def pct_change(cur, prev):
    return None if prev == 0 else (cur - prev) / prev * 100


def date_ranges(month_sel=False):
    if month_sel:
        months, today, d = [], date.today(), date(2025,1,1)
        while d <= today:
            months.append(d)
            d += relativedelta(months=1)
        sel = st.sidebar.selectbox('Select Month', [m.strftime('%B %Y') for m in months])
        sd = datetime.strptime(sel, '%B %Y').date().replace(day=1)
        ed = sd + relativedelta(months=1) - timedelta(days=1)
    else:
        ed = date.today()
        sd = ed - timedelta(days=30)
    ped = sd - timedelta(days=1)
    psd = ped - (ed - sd)
    fmt = lambda x: x.strftime('%Y-%m-%d')
    return fmt(sd), fmt(ed), fmt(psd), fmt(ped)

# Fetch functions

@st.cache_data(ttl=3600)
def get_total_users(pid, sd, ed):
    req = {'property': f'properties/{pid}',
           'date_ranges': [{'start_date': sd, 'end_date': ed}],
           'metrics': [{'name': 'totalUsers'}]}
    return int(ga4.run_report(request=req).rows[0].metric_values[0].value)

@st.cache_data(ttl=3600)
def get_traffic(pid, sd, ed):
    req = {'property': f'properties/{pid}',
           'date_ranges': [{'start_date': sd, 'end_date': ed}],
           'dimensions': [{'name': 'sessionDefaultChannelGroup'}],
           'metrics': [{'name': 'sessions'}]}
    rows = ga4.run_report(request=req).rows
    return [{'channel': r.dimension_values[0].value, 'sessions': int(r.metric_values[0].value)} for r in rows]

@st.cache_data(ttl=3600)
def get_search_console(site, sd, ed, limit=10):
    body = {'startDate': sd, 'endDate': ed, 'dimensions': ['page', 'query'], 'rowLimit': limit}
    resp = sc.searchanalytics().query(siteUrl=site, body=body).execute()
    return resp.get('rows', [])

# =========================
# SIDEBAR CONTROLS
# =========================
with st.sidebar:
    st.title('Filters')
    month_sel = st.checkbox('Select Month (vs last 30 days)')
    sd, ed, psd, ped = date_ranges(month_sel)

# =========================
# METRIC CARDS (3 columns)
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
    st.markdown('</div>', unsafe_allow_html=True)
# Sessions
with col2:
    traf = get_traffic(PROPERTY_ID, sd, ed)
    total_sess = sum(item['sessions'] for item in traf)
    prev_sess = sum(item['sessions'] for item in get_traffic(PROPERTY_ID, psd, ped))
    delta2 = pct_change(total_sess, prev_sess)
    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
    st.metric('Sessions', total_sess, f'{delta2:.2f}%')
    st.markdown('</div>', unsafe_allow_html=True)
# Organic Clicks
with col3:
    sc_rows = get_search_console(SC_SITE_URL, sd, ed)
    clicks = sum(r.get('clicks', 0) for r in sc_rows)
    prev_clicks = sum(r.get('clicks', 0) for r in get_search_console(SC_SITE_URL, psd, ped))
    delta3 = pct_change(clicks, prev_clicks)
    st.markdown('<div class="metric-container">', unsafe_allow_html=True)
    st.metric('Organic Clicks', clicks, f'{delta3:.2f}%')
    st.markdown('</div>', unsafe_allow_html=True)

# =========================
# DETAILED TABLES
# =========================
st.write('<div class="section-header"><h3>Traffic Acquisition by Channel</h3></div>', unsafe_allow_html=True)
st.table(pd.DataFrame(get_traffic(PROPERTY_ID, sd, ed)))

st.write('<div class="section-header"><h3>Top 10 Organic Queries</h3></div>', unsafe_allow_html=True)
sc_df = pd.DataFrame([{'page': r['keys'][0], 'query': r['keys'][1], 'clicks': r.get('clicks', 0)} for r in sc_rows])
st.dataframe(sc_df.head(10))

st.write('<div class="section-header"><h3>Active Users by Country (Top 5)</h3></div>', unsafe_allow_html=True)
# Reuse GA4 traffic for country by substituting in fetch method if implemented

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
