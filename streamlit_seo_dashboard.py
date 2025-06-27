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
    # Normalize private_key formatting
    raw_key = sa_info.get('private_key', '')
    formatted_key = textwrap.dedent(raw_key).strip('\n') + '\n'
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
    request = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'metrics': [{'name': 'totalUsers'}]
    }
    response = ga4_client.run_report(request=request)
    return int(response.rows[0].metric_values[0].value)


def fetch_ga4_traffic_acquisition(property_id, start_date, end_date):
    request = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'dimensions': [{'name': 'sessionDefaultChannelGroup'}],
        'metrics': [{'name': 'sessions'}]
    }
    response = ga4_client.run_report(request=request)
    return [{'channel': r.dimension_values[0].value, 'sessions': int(r.metric_values[0].value)} for r in response.rows]


def fetch_ga4_organic_landing(property_id, start_date, end_date):
    request = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date, 'end_date': end_date}],
        'dimensions': [{'name': 'landingPagePlusQueryString'}],
        'metrics': [{'name': 'sessions'}],
        'dimension_filter': {'filter': {'field_name': 'sessionDefaultChannelGroup', 'string_filter': {'value': 'Organic Search','match_type': 'EXACT'}}}
    }
    response = ga4_client.run_report(request=request)
    return [{'landingPage': r.dimension_values[0].value, 'sessions': int(r.metric_values[0].value)} for r in response.rows]


def fetch_ga4_active_users_by_country(property_id, start_date, end_date, top_n=5):
    request = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date,'end_date': end_date}],
        'dimensions': [{'name': 'country'}],
        'metrics': [{'name': 'activeUsers'}],
        'order_bys': [{'metric': {'metric_name': 'activeUsers'}, 'desc': True}],
        'limit': top_n
    }
    response = ga4_client.run_report(request=request)
    return [{'country': r.dimension_values[0].value,'activeUsers': int(r.metric_values[0].value)} for r in response.rows]


def fetch_ga4_pageviews(property_id, start_date, end_date, top_n=10):
    request = {
        'property': f'properties/{property_id}',
        'date_ranges': [{'start_date': start_date,'end_date': end_date}],
        'dimensions': [{'name': 'pageTitle'},{'name': 'screenClass'}],
        'metrics': [{'name': 'screenPageViews'}],
        'order_bys': [{'metric': {'metric_name': 'screenPageViews'}, 'desc': True}],
        'limit': top_n
    }
    response = ga4_client.run_report(request=request)
    return [{'pageTitle': r.dimension_values[0].value,'screenClass': r.dimension_values[1].value,'views': int(r.metric_values[0].value)} for r in response.rows]

# =========================
# SEARCH CONSOLE FETCH
# =========================

def fetch_sc_organic_traffic(site_url, start_date, end_date, row_limit=500):
    body = {'startDate': start_date,'endDate': end_date,'dimensions': ['page','query'],'rowLimit': row_limit}
    response = sc_service.searchanalytics().query(siteUrl=site_url, body=body).execute()
    return [{'page': r['keys'][0],'query': r['keys'][1],'clicks': r.get('clicks',0)} for r in response.get('rows',[])]

# =========================
# GOOGLE MY BUSINESS FETCH
# =========================

def fetch_gmb_metrics(location_id, start_date, end_date):
    request_body = {
        'locationNames': [f'locations/{location_id}'],
        'basicRequest': {
            'metricRequests': [],  # TODO: populate with desired GMB metrics
            'timeRange': {
                'startTime': f'{start_date}T00:00:00Z',
                'endTime': f'{end_date}T23:59:59Z'
            }
        }
    }
    return gmb_service.businessprofileperformance().report(requestBody=request_body).execute()

# =========================
# STREAMLIT APP LAYOUT
# =========================

st.title('SEO & Reporting Dashboard')
use_month = st.sidebar.checkbox('Select Month (Jan 2025 onward)')
start_date, end_date, prev_start, prev_end = get_date_ranges(use_month)

st.header('Website Analytics')
current_users = fetch_ga4_total_users(PROPERTY_ID, start_date, end_date)
previous_users = fetch_ga4_total_users(PROPERTY_ID, prev_start, prev_end)
delta_users = calculate_percentage_change(current_users, previous_users)
st.subheader('Total Users')
st.metric('Users', current_users, f'{delta_users:.2f}%')

traffic_df = pd.DataFrame(fetch_ga4_traffic_acquisition(PROPERTY_ID, start_date, end_date))
st.subheader('Traffic Acquisition by Channel')
st.table(traffic_df)

sc_df = pd.DataFrame(fetch_sc_organic_traffic(SC_SITE_URL, start_date, end_date))
st.subheader('Google Organic Search Traffic (Clicks)')
st.dataframe(sc_df.head(10))

country_df = pd.DataFrame(fetch_ga4_active_users_by_country(PROPERTY_ID, start_date, end_date))
st.subheader('Active Users by Country (Top 5)')
st.table(country_df)

pageviews_df = pd.DataFrame(fetch_ga4_pageviews(PROPERTY_ID, start_date, end_date))
st.subheader('Pages & Screens Views')
st.table(pageviews_df)

st.header('Google My Business Analytics')
gmb_data = fetch_gmb_metrics(GMB_LOCATION_ID, start_date, end_date)
st.write(gmb_data)
