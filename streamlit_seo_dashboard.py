import streamlit as st

def calculate_hlv(age, retirement_age, annual_income, annual_expenses, current_savings, inflation_rate, investment_return):
    working_years_left = retirement_age - age
    hlv = 0
    for year in range(1, working_years_left + 1):
        net_income = annual_income - annual_expenses
        discount_rate = (1 + investment_return / 100) / (1 + inflation_rate / 100) - 1
        hlv += net_income / ((1 + discount_rate) ** year)
    hlv -= current_savings
    return max(hlv, 0)

st.set_page_config(page_title="Human Life Value Calculator", layout="centered")

st.markdown(
    f"""
    <style>
    .main {{
        background-color: #ffffff;
        color: #2d448d;
        font-family: 'Segoe UI', sans-serif;
    }}
    .stSlider > div > div {{
        background-color: #2d448d;
    }}
    .stButton>button {{
        background-color: #a6ce39;
        color: white;
        border-radius: 5px;
        padding: 0.5em 1em;
        font-size: 1em;
        border: none;
    }}
    .stButton>button:hover {{
        background-color: #459fda;
    }}
    </style>
    """,
    unsafe_allow_html=True
)

st.title("🧮 Human Life Value (HLV) Calculator")

age = st.slider("Current Age", min_value=18, max_value=65, value=30)
retirement_age = st.slider("Expected Retirement Age", min_value=50, max_value=75, value=60)
annual_income = st.slider("Annual Income (₹)", min_value=100000, max_value=10000000, step=100000, value=1000000)
annual_expenses = st.slider("Annual Expenses (₹)", min_value=0, max_value=annual_income, step=50000, value=400000)
current_savings = st.slider("Current Savings (₹)", min_value=0, max_value=10000000, step=100000, value=500000)
inflation_rate = st.slider("Expected Inflation Rate (%)", min_value=0.0, max_value=15.0, step=0.1, value=6.0)
investment_return = st.slider("Expected Investment Return (%)", min_value=0.0, max_value=20.0, step=0.1, value=8.0)

if st.button("Calculate HLV"):
    hlv_result = calculate_hlv(age, retirement_age, annual_income, annual_expenses, current_savings, inflation_rate, investment_return)
    st.success(f"Your Estimated Human Life Value (HLV) is: ₹{hlv_result:,.2f}")
