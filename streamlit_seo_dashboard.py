# streamlit_seo_dashboard.py
# A minimal Streamlit-based SEO & Social Media Reporting Dashboard (up to GMB section)

# Install dependencies:
# pip install streamlit google-analytics-data google-api-python-client python-dateutil pandas requests

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
import requests

# =========================
# CONFIGURATION
# =========================
PROPERTY_ID = '356205245'             # GA4 property ID
SC_SITE_URL = 'https://www.salasarservices.com/'  # GSC property URL (with trailing slash)
GMB_LOCATION_ID = '5476847919589288630' # GMB Location ID
SCOPES = [
    'https://www.googleapis.com/auth/analytics.readonly',
    'https://www.googleapis.com/auth/webmasters.readonly',
    'https://www.googleapis.com/auth/business.manage'
]

# =========================
# AUTHENTICATION
# =========================
@st.cache_resource
def get_credentials():
    """
    Load and normalize service account credentials from Streamlit secrets.
    """
    sa = st.secrets['gcp']['service_account']
    info = dict(sa)
    # Convert literal "\\n" to real newlines in private_key
    pk = info.get('private_key', '').replace('\\n', '\n')
    if not pk.endswith('\n'):
        pk += '\n'
    info['private_key'] = pk
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)

creds = get_credentials()
# Refresh token before HTTP calls
creds.refresh(GAuthRequest())

ga4_client = BetaAnalyticsDataClient(credentials=creds)
sc_service = build('searchconsole', 'v1', credentials=creds)
# Initialize GMB client
from googleapiclient.discovery import build as build_gmb
# Use separate build to avoid shadowing
gmb_service = build_gmb('businessprofileperformance', 'v1', credentials=creds)
# gmb_service not used for HTTP fallback

# =========================
# HELPERS
# =========================

def calculate_percentage_change(cur, prev):
    if prev == 0:
        return None
    return (cur - prev) / prev * 100


def get_date_ranges(use_month=False):
    if use_month:
        # Full calendar month picker
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

# =========================
# GA4 FUNCTIONS
# =========================

def fetch_ga4_total_users(pid, sd, ed):
    req = {'property': f'properties/{pid}',
           'date_ranges': [{'start_date': sd, 'end_date': ed}],
           'metrics': [{'name': 'totalUsers'}]}
    resp = ga4_client.run_report(request=req)
    return int(resp.rows[0].metric_values[0].value)


def fetch_ga4_traffic(pid, sd, ed):
    req = {'property': f'properties/{pid}',
           'date_ranges': [{'start_date': sd, 'end_date': ed}],
           'dimensions': [{'name': 'sessionDefaultChannelGroup'}],
           'metrics': [{'name': 'sessions'}]}
    resp = ga4_client.run_report(request=req)
    return [{'channel': r.dimension_values[0].value, 'sessions': int(r.metric_values[0].value)} for r in resp.rows]


def fetch_ga4_pageviews(pid, sd, ed, top_n=10):
    # Try pageTitle + screenClass
    req = {'property': f'properties/{pid}',
           'date_ranges': [{'start_date': sd, 'end_date': ed}],
           'dimensions': [{'name': 'pageTitle'}, {'name': 'screenClass'}],
           'metrics': [{'name': 'screenPageViews'}],
           'order_bys': [{'metric': {'metric_name': 'screenPageViews'}, 'desc': True}],
           'limit': top_n}
    try:
        resp = ga4_client.run_report(request=req)
        return [{'pageTitle': r.dimension_values[0].value,
                 'screenClass': r.dimension_values[1].value,
                 'views': int(r.metric_values[0].value)} for r in resp.rows]
    except InvalidArgument:
        # Fallback to pagePath
        req2 = {'property': f'properties/{pid}',
                'date_ranges': [{'start_date': sd, 'end_date': ed}],
                'dimensions': [{'name': 'pagePath'}],
                'metrics': [{'name': 'screenPageViews'}],
                'order_bys': [{'metric': {'metric_name': 'screenPageViews'}, 'desc': True}],
                'limit': top_n}
        resp2 = ga4_client.run_report(request=req2)
        return [{'pagePath': r.dimension_values[0].value,
                 'views': int(r.metric_values[0].value)} for r in resp2.rows]

# =========================
# Search Console Function
# =========================

def fetch_sc_organic(site, sd, ed, limit=500):
    body = {'startDate': sd, 'endDate': ed, 'dimensions': ['page', 'query'], 'rowLimit': limit}
    try:
        resp = sc_service.searchanalytics().query(siteUrl=site, body=body).execute()
        rows = resp.get('rows', [])
    except HttpError as e:
        raise
    return [{'page': r['keys'][0], 'query': r['keys'][1], 'clicks': r.get('clicks', 0)} for r in rows]

# =========================
# =========================
# GOOGLE MY BUSINESS FETCH via python client
# =========================

def fetch_gmb_metrics(location_id, sd, ed):
    """
    Fetch Google My Business metrics for a location using Python client.
    Uses fetchMultiDailyMetricsTimeSeries method with specific metrics.
    """
    # Parse dates
    y1, m1, d1 = map(int, sd.split('-'))
    y2, m2, d2 = map(int, ed.split('-'))
    # Define metrics to retrieve
    metrics = ['CALL_CLICKS', 'WEBSITE_CLICKS', 'BUSINESS_DIRECTION_REQUESTS']
    try:
        resp = gmb_service.locations().fetchMultiDailyMetricsTimeSeries(
            location=f'locations/{location_id}',
            dailyMetrics=metrics,
            dailyRange_startDate_year=y1,
            dailyRange_startDate_month=m1,
            dailyRange_startDate_day=d1,
            dailyRange_endDate_year=y2,
            dailyRange_endDate_month=m2,
            dailyRange_endDate_day=d2
        ).execute()
        return resp
    except HttpError as err:
        status = getattr(err, 'status_code', 'Unknown')
        details = getattr(err, 'error_details', '') or str(err)
        return {'error': f'HTTP {status}: {details}'}
    except Exception as e:
        return {'error': str(e)}

# =========================

st.title('SEO & Reporting Dashboard')
use_month = st.sidebar.checkbox('Select Month (Jan 2025 onward)')
sd, ed, ps, ped = get_date_ranges(use_month)

# Website Analytics
st.header('Website Analytics')
users = fetch_ga4_total_users(PROPERTY_ID, sd, ed)
prev_users = fetch_ga4_total_users(PROPERTY_ID, ps, ped)
delta = calculate_percentage_change(users, prev_users)
st.subheader('Total Users')
st.metric('Users', users, f'{delta:.2f}%')

st.subheader('Traffic Acquisition by Channel')
st.table(pd.DataFrame(fetch_ga4_traffic(PROPERTY_ID, sd, ed)))

st.subheader('Google Organic Search Traffic (Clicks)')
try:
    sc_df = pd.DataFrame(fetch_sc_organic(SC_SITE_URL, sd, ed)).head(10)
    st.dataframe(sc_df)
except HttpError:
    st.error('Search Console API error: check permissions & API enabled')

st.subheader('Active Users by Country (Top 5)')
st.table(pd.DataFrame(fetch_ga4_traffic(PROPERTY_ID, sd, ed)).head(5))

st.subheader('Pages & Screens Views')
try:
    st.table(pd.DataFrame(fetch_ga4_pageviews(PROPERTY_ID, sd, ed)))
except InvalidArgument:
    st.error('GA4 API error: views not available')

# Google My Business Analytics
st.header('Google My Business Analytics')
gmb = fetch_gmb_metrics(GMB_LOCATION_ID, sd, ed)
if isinstance(gmb, dict) and 'error' in gmb:
    st.error(f"Google My Business API Error: {gmb['error']}")
else:
    st.json(gmb)
