# streamlit_seo_dashboard.py
# A minimal Streamlit-based SEO & Reporting Dashboard up to Google My Business section

# Install dependencies before running:
# pip install streamlit google-analytics-data google-api-python-client python-dateutil pandas

import streamlit as st
import textwrap
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from googleapiclient.discovery import build
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd
from google.api_core.exceptions import InvalidArgument
from googleapiclient.errors import HttpError

# =========================
# CONFIGURATION
# =========================
PROPERTY_ID = '356205245'  # GA4 property ID
SC_SITE_URL = 'https://www.salasarservices.com/'  # GSC site URL (must include trailing slash)
GMB_LOCATION_ID = '5476847919589288630'  # GMB location ID
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
    Load service account credentials from Streamlit Secrets.
    Debug prints service account content to inspect formatting.
    """
    sa_secrets = st.secrets['gcp']['service_account']
    sa_info = dict(sa_secrets)  # make mutable copy
    # DEBUG: inspect loaded keys & preview
    st.write("SERVICE ACCOUNT FIELDS:", list(sa_info.keys()))
    st.write("PRIVATE KEY PREVIEW (first 200 chars):", sa_info.get('private_key', '')[:200])
    # Normalize private_key formatting: convert literal "\\n" sequences to actual newlines
    raw_key = sa_info.get('private_key', '')
    formatted_key = raw_key.replace('\\n', '\n')
    # Ensure key ends with a newline
    if not formatted_key.endswith('\n'):
        formatted_key += '\n'
    sa_info['private_key'] = formatted_key
    creds = service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)
    return creds

# Initialize API clients
creds = get_credentials()
ga4_client = BetaAnalyticsDataClient(credentials=creds)
sc_service = build('searchconsole', 'v1', credentials=creds)
gmb_service = build('businessprofileperformance', 'v1', credentials=creds)

# =========================
# HELPER FUNCTIONS
# =========================

def calculate_percentage_change(current, previous):
    """
    Return percentage change between current and previous values.
    """
    if previous == 0:
        return None
    return (current - previous) / previous * 100


def get_date_ranges(use_month_selector=False):
    """
    Determine date ranges for current and previous periods.
    Returns start_date, end_date, prev_start, prev_end as YYYY-MM-DD strings.
    """
    if use_month_selector:
        months, today, start = [], date.today(), date(2025, 1, 1)
        while start <= today:
            months.append(start)
            start += relativedelta(months=1)
        sel = st.sidebar.selectbox('Select month', [m.strftime('%B %Y') for m in months])
        sel_date = datetime.strptime(sel, '%B %Y').date()
        start_date = sel_date.replace(day=1)
        end_date = start_date + relativedelta(months=1) - timedelta(days=1)
    else:
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - (end_date - start_date)
    fmt = lambda d: d.strftime('%Y-%m-%d')
    return fmt(start_date), fmt(end_date), fmt(prev_start), fmt(prev_end)

# =========================
# GA4 FETCH FUNCTIONS
# =========================

def fetch_ga4_total_users(property_id, start_date, end_date):
    req = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'metrics': [{'name': 'totalUsers'}]
    }
    resp = ga4_client.run_report(request=req)
    return int(resp.rows[0].metric_values[0].value)


def fetch_ga4_traffic_acquisition(property_id, start_date, end_date):
    req = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'dimensions': [{'name': 'sessionDefaultChannelGroup'}],
        'metrics': [{'name': 'sessions'}]
    }
    resp = ga4_client.run_report(request=req)
    return [{'channel': r.dimension_values[0].value, 'sessions': int(r.metric_values[0].value)} for r in resp.rows]


def fetch_ga4_organic_landing(property_id, start_date, end_date):
    req = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'dimensions': [{'name': 'landingPagePlusQueryString'}],
        'metrics': [{'name': 'sessions'}],
        'dimension_filter': {
            'filter': {
                'field_name': 'sessionDefaultChannelGroup',
                'string_filter': {'value': 'Organic Search', 'match_type': 'EXACT'}
            }
        }
    }
    resp = ga4_client.run_report(request=req)
    return [{'landingPage': r.dimension_values[0].value, 'sessions': int(r.metric_values[0].value)} for r in resp.rows]


def fetch_ga4_active_users_by_country(property_id, start_date, end_date, top_n=5):
    req = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'dimensions': [{'name': 'country'}],
        'metrics': [{'name': 'activeUsers'}],
        'order_bys': [{'metric': {'metric_name': 'activeUsers'}, 'desc': True}],
        'limit': top_n
    }
    resp = ga4_client.run_report(request=req)
    return [{'country': r.dimension_values[0].value, 'activeUsers': int(r.metric_values[0].value)} for r in resp.rows]


def fetch_ga4_pageviews(property_id, start_date, end_date, top_n=10):
    """
    Fetch top N page titles + screen classes by views.
    Falls back to pagePath if pageTitle+screenClass not available.
    """
    # Primary request: pageTitle + screenClass
    req = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'dimensions': [{'name': 'pageTitle'}, {'name': 'screenClass'}],
        'metrics': [{'name': 'screenPageViews'}],
        'order_bys': [{'metric': {'metric_name': 'screenPageViews'}, 'desc': True}],
        'limit': top_n
    }
    try:
        resp = ga4_client.run_report(request=req)
        return [
            {'pageTitle': r.dimension_values[0].value,
             'screenClass': r.dimension_values[1].value,
             'views': int(r.metric_values[0].value)}
            for r in resp.rows
        ]
    except InvalidArgument:
        # Fallback: only pagePath
        req2 = {
            'property': f'properties/{property_id}',
            'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
            'dimensions': [{'name': 'pagePath'}],
            'metrics': [{'name': 'screenPageViews'}],
            'order_bys': [{'metric': {'metric_name': 'screenPageViews'}, 'desc': True}],
            'limit': top_n
        }
        resp2 = ga4_client.run_report(request=req2)
        return [
            {'pagePath': r.dimension_values[0].value,
             'views': int(r.metric_values[0].value)}
            for r in resp2.rows
        ]

# =========================
# SEARCH CONSOLE FETCH
# =========================

def fetch_sc_organic_traffic(site_url, start_date, end_date, row_limit=500):
    body = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['page', 'query'],
        'rowLimit': row_limit
    }
    resp = sc_service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    return [{'page': r['keys'][0], 'query': r['keys'][1], 'clicks': r.get('clicks', 0)} for r in resp.get('rows', [])]

# =========================
# GOOGLE MY BUSINESS FETCH
# =========================

def fetch_gmb_metrics(location_id, start_date, end_date):
    """
    Fetch Google My Business metrics for a location between dates using the Business Profile Performance API.
    """
    # Build the request body for the API
    req_body = {
        'basicRequest': {
            'metricRequests': [
                # TODO: e.g. {'metric': 'VIEWS'}, {'metric': 'SEARCH_IMPRESSIONS'}, etc.
            ],
            'timeRange': {
                'startTime': f'{start_date}T00:00:00Z',
                'endTime': f'{end_date}T23:59:59Z'
            }
        }
    }
    # The Business Profile Performance API expects the location in the path
    # Use the locations().reportInsights() method
    response = gmb_service.locations().reportInsights(
        name=f'locations/{location_id}',
        body=req_body
    ).execute()
    # Return the insights response directly
    return response

# =========================
# STREAMLIT APP LAYOUT
# =========================

st.title('SEO & Reporting Dashboard')

# Date selection controls
use_month = st.sidebar.checkbox('Select Month (Jan 2025 onward)')
start_date, end_date, prev_start, prev_end = get_date_ranges(use_month)

# --- Website Analytics ---
st.header('Website Analytics')

# Total Users metric with MoM comparison
cur_users = fetch_ga4_total_users(PROPERTY_ID, start_date, end_date)
prev_users = fetch_ga4_total_users(PROPERTY_ID, prev_start, prev_end)
delta_users = calculate_percentage_change(cur_users, prev_users)
st.subheader('Total Users')
st.metric(label='Users', value=cur_users, delta=f"{delta_users:.2f}%")

# Traffic Acquisition
traf = fetch_ga4_traffic_acquisition(PROPERTY_ID, start_date, end_date)
traf_df = pd.DataFrame(traf)
st.subheader('Traffic Acquisition by Channel')
st.table(traf_df)

# Organic Search Traffic
st.subheader('Google Organic Search Traffic (Clicks)')
try:
    org_rows = fetch_sc_organic_traffic(SC_SITE_URL, start_date, end_date)
    org_df = pd.DataFrame(org_rows)
    st.dataframe(org_df.head(10))
except HttpError:
    st.error("Search Console API error: please ensure the service account has been granted permission in Search Console and the API is enabled.")
    st.error("Search Console API error: please ensure the service account has been granted permission in Search Console and the API is enabled.")

# Active Users by Country
cnt = fetch_ga4_active_users_by_country(PROPERTY_ID, start_date, end_date)
cnt_df = pd.DataFrame(cnt)
st.subheader('Active Users by Country (Top 5)')
st.table(cnt_df)

# Page & Screen Views
st.subheader('Pages & Screens Views')
try:
    pv = fetch_ga4_pageviews(PROPERTY_ID, start_date, end_date)
    pv_df = pd.DataFrame(pv)
    st.table(pv_df)
except InvalidArgument:
    st.error("GA4 API error: 'pageTitle' and 'screenClass' or 'screenPageViews' may not be available for this property.")

# --- Google My Business Analytics ---
st.header('Google My Business Analytics')
gmb = fetch_gmb_metrics(GMB_LOCATION_ID, start_date, end_date)
st.write(gmb)
