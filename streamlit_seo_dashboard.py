# streamlit_seo_dashboard.py
# A minimal Streamlit-based SEO & Reporting Dashboard up to Google My Business section

# Install dependencies before running:
# pip install streamlit google-analytics-data google-api-python-client python-dateutil pandas

import streamlit as st
import textwrap
from google.oauth2 import service_account
from google.analytics.data_v1beta import BetaAnalyticsDataClient
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.api_core.exceptions import InvalidArgument
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
    """
    sa_secrets = st.secrets['gcp']['service_account']
    sa_info = dict(sa_secrets)
    # Normalize private_key: convert literal "\\n" to newline
    raw_key = sa_info.get('private_key', '')
    pem = raw_key.replace('\\n', '\n')
    if not pem.endswith('\n'):
        pem += '\n'
    sa_info['private_key'] = pem
    return service_account.Credentials.from_service_account_info(sa_info, scopes=SCOPES)

# Initialize clients
creds = get_credentials()
ga4_client = BetaAnalyticsDataClient(credentials=creds)
sc_service = build('searchconsole', 'v1', credentials=creds)
gmb_service = build('businessprofileperformance', 'v1', credentials=creds)

# =========================
# HELPERS
# =========================

def calculate_percentage_change(cur, prev):
    if prev == 0:
        return None
    return (cur - prev) / prev * 100


def get_date_ranges(use_month=False):
    if use_month:
        months, today, d = [], date.today(), date(2025,1,1)
        while d <= today:
            months.append(d)
            d += relativedelta(months=1)
        sel = st.sidebar.selectbox('Month', [m.strftime('%B %Y') for m in months])
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
# GA4 FETCH
# =========================

def fetch_ga4_total_users(pid, sd, ed):
    req = {'property': f'properties/{pid}', 'date_ranges': [{'start_date': sd,'end_date': ed}], 'metrics': [{'name':'totalUsers'}]}
    return int(ga4_client.run_report(request=req).rows[0].metric_values[0].value)


def fetch_ga4_traffic(pid, sd, ed):
    req = {'property': f'properties/{pid}', 'date_ranges': [{'start_date': sd,'end_date': ed}], 'dimensions':[{'name':'sessionDefaultChannelGroup'}], 'metrics':[{'name':'sessions'}]}
    rows = ga4_client.run_report(request=req).rows
    return [{'channel':r.dimension_values[0].value,'sessions':int(r.metric_values[0].value)} for r in rows]


def fetch_ga4_pageviews(pid, sd, ed, top_n=10):
    req = {'property':f'properties/{pid}','date_ranges':[{'start_date':sd,'end_date':ed}],'dimensions':[{'name':'pageTitle'},{'name':'screenClass'}],'metrics':[{'name':'screenPageViews'}],'order_bys':[{'metric':{'metric_name':'screenPageViews'},'desc':True}],'limit':top_n}
    try:
        rows=ga4_client.run_report(request=req).rows
        return [{'pageTitle':r.dimension_values[0].value,'screenClass':r.dimension_values[1].value,'views':int(r.metric_values[0].value)} for r in rows]
    except InvalidArgument:
        req2={'property':f'properties/{pid}','date_ranges':[{'start_date':sd,'end_date':ed}],'dimensions':[{'name':'pagePath'}],'metrics':[{'name':'screenPageViews'}],'order_bys':[{'metric':{'metric_name':'screenPageViews'},'desc':True}],'limit':top_n}
        rows2=ga4_client.run_report(request=req2).rows
        return [{'pagePath':r.dimension_values[0].value,'views':int(r.metric_values[0].value)} for r in rows2]

# =========================
# Search Console
# =========================

def fetch_sc_organic(site, sd, ed, limit=500):
    body={'startDate':sd,'endDate':ed,'dimensions':['page','query'],'rowLimit':limit}
    rows=sc_service.searchanalytics().query(siteUrl=site,body=body).execute().get('rows',[])
    return [{'page':r['keys'][0],'query':r['keys'][1],'clicks':r.get('clicks',0)} for r in rows]

# =========================
# GMB FETCH
# =========================

def fetch_gmb_metrics(location_id, start_date, end_date):
    """
    Fetch Google My Business metrics for a location using GMB API.
    Uses fetchMultiDailyMetricsTimeSeries with 'parent' parameter only.
    """
    req_body = {
        'dailyMetricsOptions': {
            'timeRange': {
                'startTime': f'{start_date}T00:00:00Z',
                'endTime': f'{end_date}T23:59:59Z'
            },
            'metricRequests': [
                {'metric': 'ALL'}
            ]
        }
    }
    try:
        # Only use 'parent' arg; 'name' is not supported
        response = gmb_service.locations().fetchMultiDailyMetricsTimeSeries(
            parent=f'locations/{location_id}',
            body=req_body
        ).execute()
        return response
    except HttpError as err:
        # Return structured error for display
        status = getattr(err, 'status_code', 'Unknown')
        details = getattr(err, 'error_details', '') or str(err)
        return {'error': f'HTTP {status}: {details}'}
    except Exception as err:
        return {'error': str(err)}

# =========================
# STREAMLIT LAYOUT
# =========================

st.title('SEO & Reporting Dashboard')
# Date range selection: last 30 days or full calendar month
use_month = st.sidebar.checkbox('Select Month (Jan 2025 onward)')
# Returns: start_date, end_date, prev_start_date, prev_end_date
sd, ed, ps, ped = get_date_ranges(use_month)

# Website Analytics
st.header('Website Analytics')
users=fetch_ga4_total_users(PROPERTY_ID,sd,ed)
pusers=fetch_ga4_total_users(PROPERTY_ID,ps,ped)
delta=calculate_percentage_change(users,pusers)
st.subheader('Total Users')
st.metric('Users',users,f"{delta:.2f}%")

st.subheader('Traffic Acquisition by Channel')
st.table(pd.DataFrame(fetch_ga4_traffic(PROPERTY_ID,sd,ed)))

st.subheader('Google Organic Search Traffic (Clicks)')
try:
    df_sc=pd.DataFrame(fetch_sc_organic(SC_SITE_URL,sd,ed)).head(10)
    st.dataframe(df_sc)
except HttpError:
    st.error('Search Console API error')

st.subheader('Active Users by Country (Top 5)')
st.table(pd.DataFrame(fetch_ga4_traffic(PROPERTY_ID,sd,ed)).head(5))

st.subheader('Pages & Screens Views')
try:
    st.table(pd.DataFrame(fetch_ga4_pageviews(PROPERTY_ID,sd,ed)))
except InvalidArgument:
    st.error('GA4 API error: views not available')

# Google My Business Analytics
st.header('Google My Business Analytics')
gmb=fetch_gmb_metrics(GMB_LOCATION_ID,sd,ed)
if isinstance(gmb,dict) and 'error' in gmb:
    st.error(f"GMB API Error: {gmb['error']}")
else:
    st.json(gmb)
