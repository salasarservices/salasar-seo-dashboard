# app.py
# Streamlit Social Media Analytics Dashboard
# This app fetches Facebook and LinkedIn metrics and displays month-over-month comparisons.

import os
import requests
import datetime
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# --------------------------------------
# Load environment variables from .env file
# --------------------------------------
load_dotenv()

# Facebook credentials
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
FB_ACCESS_TOKEN = os.getenv("FB_ACCESS_TOKEN")
FB_API_BASE = "https://graph.facebook.com/v12.0"

# LinkedIn credentials
LI_ACCESS_TOKEN = os.getenv("LI_ACCESS_TOKEN")
LI_ORG_URN = os.getenv("LI_ORG_URN")
LI_API_BASE = "https://api.linkedin.com/v2"

li_headers = {
    "Authorization": f"Bearer {LI_ACCESS_TOKEN}"
}

# --------------------------------------
# Helper: Date range calculation
# --------------------------------------
def get_date_ranges(days=30):
    """
    Return tuples for current period and previous period as (since, until).
    """
    today = datetime.date.today()
    until = today
    since = today - datetime.timedelta(days=days)
    prev_until = since
    prev_since = since - datetime.timedelta(days=days)
    return (since, until), (prev_since, prev_until)

# --------------------------------------
# Section: Facebook metrics
# --------------------------------------
# Function to fetch aggregated insight for a metric over a date range
def fb_get_insight(metric, since, until):
    """
    Fetch Facebook Page insight metric values for a given date range.
    Returns the sum of all daily values.
    """
    url = f"{FB_API_BASE}/{FB_PAGE_ID}/insights"
    params = {
        "metric": metric,
        "since": since.isoformat(),
        "until": until.isoformat(),
        "access_token": FB_ACCESS_TOKEN
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    values = [item.get("value", 0) 
              for item in data.get("data", [{}])[0].get("values", [])]
    return sum(values)

# Compute Facebook metrics and month-over-month changes
(current_range, prev_range) = get_date_ranges(30)
fb_metrics = {
    "Post Reach": "page_posts_impressions_unique",
    "Post Engagement": "page_engaged_users",
    "New Page Likes": "page_fan_adds_unique",
    # 'page_fans' gives total fans; new followers usually align with likes
    "New Page Followers": "page_fan_adds_unique"
}

fb_results = {}
for label, metric_name in fb_metrics.items():
    curr = fb_get_insight(metric_name, *current_range)
    prev = fb_get_insight(metric_name, *prev_range)
    change = ((curr - prev) / prev * 100) if prev != 0 else None
    fb_results[label] = {"current": curr, "previous": prev, "change": change}

# Fetch breakdowns: Age & Gender and Top Cities
# Facebook provides these as 'lifetime' snapshots

def fb_get_breakdown(metric, period="lifetime"):
    """
    Fetch Facebook breakdown metrics (demographics or location).
    """
    url = f"{FB_API_BASE}/{FB_PAGE_ID}/insights"
    params = {
        "metric": metric,
        "period": period,
        "access_token": FB_ACCESS_TOKEN
    }
    resp = requests.get(url, params=params)
    data = resp.json()
    return data.get("data", [{}])[0].get("values", [{}])[0].get("value", {})

age_gender = fb_get_breakdown("page_fans_gender_age")
city_counts = fb_get_breakdown("page_fans_city")

# --------------------------------------
# Section: LinkedIn metrics
# --------------------------------------
def li_get_page_stats(start, end, org_urn=LI_ORG_URN):
    """
    Fetch page_views and uniquePageViews over a date range.
    """
    params = {
        "q": "organization",
        "organization": org_urn,
        "timeIntervals": f"(timeRange:(start:{start.strftime('%Y%m%d')},end:{end.strftime('%Y%m%d')}),timeGranularityType:DAY)"
    }
    url = f"{LI_API_BASE}/organizationalEntityPageStatistics"
    resp = requests.get(url, headers=li_headers, params=params)
    data = resp.json()
    views = sum(elem.get("views", 0) for elem in data.get("elements", []))
    uniques = sum(elem.get("uniquePageViews", 0) for elem in data.get("elements", []))
    return views, uniques


def li_get_follower_stats(start, end, org_urn=LI_ORG_URN):
    """
    Fetch total and new followers over a date range.
    """
    params = {
        "q": "organizationalEntityFollowerStatistics",
        "organizationalEntity": org_urn,
        "timeIntervals": f"(timeRange:(start:{start.strftime('%Y%m%d')},end:{end.strftime('%Y%m%d')}),timeGranularityType:DAY)"
    }
    url = f"{LI_API_BASE}/organizationalEntityFollowerStatistics"
    resp = requests.get(url, headers=li_headers, params=params)
    data = resp.json()
    new_followers = sum(elem.get("newFollowerCount", 0) for elem in data.get("elements", []))
    total_followers = data.get("paging", {}).get("total", None)
    return total_followers, new_followers


def li_get_post_engagement(start, end, org_urn=LI_ORG_URN):
    """
    Fetch share count and engagement rate over a date range.
    """
    params = {
        "q": "organizationShares",
        "organization": org_urn,
        "sharesPerOwner": False,
        "timeIntervals": f"(timeRange:(start:{start.strftime('%Y%m%d')},end:{end.strftime('%Y%m%d')}),timeGranularityType:DAY)"
    }
    url = f"{LI_API_BASE}/organizationalEntityShareStatistics"
    resp = requests.get(url, headers=li_headers, params=params)
    data = resp.json()
    total_shares = sum(elem.get("totalShareStatistics", {}).get("shareCount", 0) for elem in data.get("elements", []))
    total_engagements = sum(elem.get("totalShareStatistics", {}).get("engagement", 0) for elem in data.get("elements", []))
    rate = (total_engagements / total_shares) if total_shares else None
    return total_shares, rate

# Compute LinkedIn metrics
(li_curr_range, li_prev_range) = get_date_ranges(30)
li_results = {}
# Visitor Highlights
cv, cu = li_get_page_stats(*li_curr_range)
pv, pu = li_get_page_stats(*li_prev_range)
li_results['Visitor Highlights'] = {'Page Views': {'current': cv, 'previous': pv},
                                   'Unique Visitors': {'current': cu, 'previous': pu}}
# Follower Highlights
ct, cn = li_get_follower_stats(*li_curr_range)
pt, pn = li_get_follower_stats(*li_prev_range)
li_results['Follower Highlights'] = {'Total Followers': {'current': ct, 'previous': pt},
                                    'New Followers': {'current': cn, 'previous': pn}}
# Competitor Highlights (self)
csh, cr = li_get_post_engagement(*li_curr_range)
psh, pr = li_get_post_engagement(*li_prev_range)
li_results['Competitor Highlights'] = {'Post Count': {'current': csh, 'previous': psh},
                                      'Engagement Rate': {'current': cr, 'previous': pr}}

# --------------------------------------
# Section: Streamlit UI
# --------------------------------------
st.title("Social Media Analytics")

# Facebook Section
st.header("Facebook")
for metric, vals in fb_results.items():
    st.subheader(metric)
    delta = f"{vals['change']:.2f}%" if vals['change'] is not None else "N/A"
    st.metric(label="Last 30 Days", value=vals['current'], delta=delta)

# Audience age/gender breakdown
st.subheader("Audience - Age & Gender")
age_gender_df = pd.DataFrame(age_gender.items(), columns=["Age & Gender", "Count"])
st.table(age_gender_df)

# Location: top 10 cities
st.subheader("Location - Top 10 Cities")
city_df = pd.DataFrame(city_counts.items(), columns=["City", "Count"]).sort_values("Count", ascending=False).head(10)
st.table(city_df)

# LinkedIn Section
st.header("LinkedIn")
# Visitor highlights
st.subheader("Visitor Highlights")
for label, v in li_results['Visitor Highlights'].items():
    change = ((v['current'] - v['previous']) / v['previous'] * 100) if v['previous'] else None
    delta = f"{change:.2f}%" if change is not None else "N/A"
    st.metric(label, v['current'], delta)

# Follower highlights
st.subheader("Follower Highlights")
for label, v in li_results['Follower Highlights'].items():
    change = ((v['current'] - v['previous']) / v['previous'] * 100) if v['previous'] else None
    delta = f"{change:.2f}%" if change is not None else "N/A"
    st.metric(label, v['current'], delta)

# Competitor highlights
st.subheader("Competitor Highlights")
for label, v in li_results['Competitor Highlights'].items():
    change = ((v['current'] - v['previous']) / v['previous'] * 100) if v['previous'] else None
    delta = f"{change:.2f}%" if change is not None else "N/A"
    st.metric(label, v['current'], delta)
