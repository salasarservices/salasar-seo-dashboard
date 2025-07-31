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
# STREAMLIT APP LAYOUT (continued)

...  # previous sections above remain unchanged

# --- Google My Business Analytics ---
st.header('Google My Business Analytics')
try:
    gmb = fetch_gmb_metrics(GMB_LOCATION_ID, start_date, end_date)
    if isinstance(gmb, dict) and gmb.get('error'):
        st.error(f"GMB API Error: {gmb['error']}")
    else:
        st.json(gmb)
except Exception as e:
    st.error(f"Unable to load Google My Business data: {e}")
