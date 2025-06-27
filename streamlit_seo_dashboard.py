# streamlit_seo_dashboard.py
# A minimal Streamlit-based SEO & Reporting Dashboard up to Google My Business section

# Install dependencies before running:
# pip install streamlit google-analytics-data google-api-python-client python-dateutil pandas

import streamlit as st
import json
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from googleapiclient.discovery import build
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import pandas as pd

# =========================
# CONFIGURATION
# =========================
# Google Analytics 4 property ID
PROPERTY_ID = '356205245'

# Google Search Console site URL
SC_SITE_URL = 'https://www.salasarservices.com/'

# Google My Business location ID
GMB_LOCATION_ID = '5476847919589288630'

# Combined scopes for Analytics, Search Console, and GMB
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
    """
    sa_info = json.loads(st.secrets["gcp"]["service_account"])
    creds = service_account.Credentials.from_service_account_info(
        sa_info,
        scopes=SCOPES
    )
    return creds

creds = get_credentials()

# Initialize Google API clients
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
    - By default: last 30 days vs. the 30 days before that.
    - If month selector: picks a full calendar month and compares to previous month.
    Returns: start_date, end_date, prev_start_date, prev_end_date (all YYYY-MM-DD strings)
    """
    if use_month_selector:
        # Build list of months from Jan 2025 to now
        months = []
        current = date.today()
        start = date(2025, 1, 1)
        while start <= current:
            months.append(start)
            start += relativedelta(months=1)
        # Let user pick
        sel = st.sidebar.selectbox('Select month', [m.strftime('%B %Y') for m in months])
        # Parse selected month
        sel_date = datetime.strptime(sel, '%B %Y').date()
        start_date = sel_date.replace(day=1)
        end_date = (start_date + relativedelta(months=1) - timedelta(days=1))
    else:
        end_date = date.today()
        start_date = end_date - timedelta(days=30)

    # Previous period is same length immediately before current
    prev_end = start_date - timedelta(days=1)
    prev_start = prev_end - (end_date - start_date)

    fmt = lambda d: d.strftime('%Y-%m-%d')
    return fmt(start_date), fmt(end_date), fmt(prev_start), fmt(prev_end)

# =========================
# GA4 FETCH FUNCTIONS
# =========================

def fetch_ga4_total_users(property_id, start_date, end_date):
    """
    Fetch total users from GA4 for the given date range.
    """
    request = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'metrics': [{'name': 'totalUsers'}]
    }
    response = ga4_client.run_report(request=request)
    return int(response.rows[0].metric_values[0].value)


def fetch_ga4_traffic_acquisition(property_id, start_date, end_date):
    """
    Fetch session counts by default channel group from GA4.
    """
    request = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'dimensions': [{'name': 'sessionDefaultChannelGroup'}],
        'metrics': [{'name': 'sessions'}]
    }
    response = ga4_client.run_report(request=request)
    data = []
    for row in response.rows:
        channel = row.dimension_values[0].value
        sessions = int(row.metric_values[0].value)
        data.append({'channel': channel, 'sessions': sessions})
    return data


def fetch_ga4_organic_landing(property_id, start_date, end_date):
    """
    Fetch organic search sessions by landing page + query string.
    """
    request = {
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
    response = ga4_client.run_report(request=request)
    return [
        {
            'landingPage': row.dimension_values[0].value,
            'sessions': int(row.metric_values[0].value)
        }
        for row in response.rows
    ]


def fetch_ga4_active_users_by_country(property_id, start_date, end_date, top_n=5):
    """
    Fetch top N countries by active users.
    """
    request = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'dimensions': [{'name': 'country'}],
        'metrics': [{'name': 'activeUsers'}],
        'order_bys': [{'metric': {'metric_name': 'activeUsers'}, 'desc': True}],
        'limit': top_n
    }
    response = ga4_client.run_report(request=request)
    return [
        {'country': row.dimension_values[0].value, 'activeUsers': int(row.metric_values[0].value)}
        for row in response.rows
    ]


def fetch_ga4_pageviews(property_id, start_date, end_date, top_n=10):
    """
    Fetch top N page titles + screen classes by views.
    """
    request = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'dimensions': [{'name': 'pageTitle'}, {'name': 'screenClass'}],
        'metrics': [{'name': 'screenPageViews'}],
        'order_bys': [{'metric': {'metric_name': 'screenPageViews'}, 'desc': True}],
        'limit': top_n
    }
    response = ga4_client.run_report(request=request)
    data = []
    for row in response.rows:
        data.append({
            'pageTitle': row.dimension_values[0].value,
            'screenClass': row.dimension_values[1].value,
            'views': int(row.metric_values[0].value)
        })
    return data

# =========================
# SEARCH CONSOLE FETCH
# =========================

def fetch_sc_organic_traffic(site_url, start_date, end_date, row_limit=500):
    """
    Fetch clicks by landing page + query from Search Console.
    """
    body = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['page', 'query'],
        'rowLimit': row_limit
    }
    resp = sc_service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    rows = resp.get('rows', [])
    return [
        {
            'page': r['keys'][0],
            'query': r['keys'][1],
            'clicks': r.get('clicks', 0)
        }
        for r in rows
    ]

# =========================
# GOOGLE MY BUSINESS FETCH
# =========================

def fetch_gmb_metrics(location_id, start_date, end_date):
    """
    Fetch GMB metrics for a location between dates.
    TODO: Adjust service and fields per the Business Profile Performance API documentation.
    """
    request_body = {
        'locationNames': [f'locations/{location_id}'],
        'basicRequest': {
            'metricRequests': [
                # e.g. {'metric': 'TOTAL_VIEWS'}, etc.
            ],
            'timeRange': {
                'startTime': f'{start_date}T00:00:00Z',
                'endTime': f'{end_date}T23:59:59Z'
            }
        }
    }
    response = gmb_service.businessprofileperformance().report(requestBody=request_body).execute()
    return response

# =========================
# STREAMLIT APP LAYOUT
# =========================

st.title('SEO & Reporting Dashboard')

# Date range controls
use_month = st.sidebar.checkbox('Select Month (Jan 2025 onward)')
start_date, end_date, prev_start, prev_end = get_date_ranges(use_month)

# --- Website Analytics ---
st.header('Website Analytics')

# Total Users
current_users = fetch_ga4_total_users(PROPERTY_ID, start_date, end_date)
previous_users = fetch_ga4_total_users(PROPERTY_ID, prev_start, prev_end)
delta_users = calculate_percentage_change(current_users, previous_users)
st.subheader('Total Users')
st.metric('Users', current_users, f'{delta_users:.2f}%')

# Traffic Acquisition
traffic_df = pd.DataFrame(fetch_ga4_traffic_acquisition(PROPERTY_ID, start_date, end_date))
st.subheader('Traffic Acquisition by Channel')
st.table(traffic_df)

# Google Organic Search Traffic
sc_df = pd.DataFrame(fetch_sc_organic_traffic(SC_SITE_URL, start_date, end_date))
st.subheader('Google Organic Search Traffic (Clicks)')
st.dataframe(sc_df.head(10))

# Active Users by Country
country_df = pd.DataFrame(fetch_ga4_active_users_by_country(PROPERTY_ID, start_date, end_date))
st.subheader('Active Users by Country (Top 5)')
st.table(country_df)

# Pages and Screens Views
pageviews_df = pd.DataFrame(fetch_ga4_pageviews(PROPERTY_ID, start_date, end_date))
st.subheader('Pages & Screens Views')
st.table(pageviews_df)

# --- Google My Business Analytics ---
st.header('Google My Business Analytics')

# Profile Metrics
gmb_data = fetch_gmb_metrics(GMB_LOCATION_ID, start_date, end_date)
st.write(gmb_data)
