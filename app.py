import io
import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from streamlit_option_menu import option_menu


# our helpers (already written earlier)
from data import load_all          # uses your 01.xlsx + optional 02_budget.xlsx and maps account_group correctly
from metrics import kpis, monthly_pnl
from charts import kpi_card_md, donut, line_two, waterfall_from_monthly, inject_watermark



# --------------------
# Page & watermark
# --------------------
st.set_page_config(page_title="Financial Performance", layout="wide")


# Widen the main content container a bit
st.markdown("""
<style>
.block-container { max-width: 1500px; padding-top: 0.5rem; padding-bottom: 0.5rem; }
</style>
""", unsafe_allow_html=True)

inject_watermark(st, "logo.png")

# --------------------
# Load data (DO NOT edit your files)
# --------------------
try:
    tx, bd = load_all()   # tx has: account_group in {"Revenue","COGS","OPEX"} and signed_amount (+/-) ready
except Exception as e:
    st.error(f"Data loading error: {e}")
    st.stop()

# --------------------
# Optional: user uploads to update/append data
# --------------------
def _read_any_table(uploaded):
    if uploaded.name.lower().endswith(".csv"):
        df = pd.read_csv(uploaded)
    else:
        # default to excel; reads first sheet
        df = pd.read_excel(uploaded)
    return df

def _ensure_period_cols(df):
    # create year/month if we have a date column
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["year"] = df["date"].dt.year
        df["month"] = df["date"].dt.month
    return df

def _normalize_uploaded_tx(df, tx_template):
    """
    Make uploaded 01-like data look like current tx:
    - keep only columns that exist in your current tx
    - if signed_amount missing but AMOUNT present, derive sign from account_group
    - ensure date/year/month exist
    """
    df = df.copy()
    df = _ensure_period_cols(df)

    # derive signed_amount if needed
    if "signed_amount" not in df.columns and "AMOUNT" in df.columns:
        if "account_group" in df.columns:
            df["signed_amount"] = df["AMOUNT"].where(
                df["account_group"].eq("Revenue"),
                -df["AMOUNT"].abs()
            )
        else:
            # fall back: assume AMOUNT already signed
            df["signed_amount"] = pd.to_numeric(df["AMOUNT"], errors="coerce")

    # keep only columns that already exist in your tx (avoids schema surprises)
    keep = [c for c in df.columns if c in tx_template.columns]
    df = df[keep]

    # also make sure dtypes are friendly
    if "signed_amount" in df.columns:
        df["signed_amount"] = pd.to_numeric(df["signed_amount"], errors="coerce").fillna(0)

    return df

def _normalize_uploaded_budget(df, bd_template):
    """
    Make uploaded 02_budget-like data look like current bd:
    - try to find budget_amount/date/account_group
    - ensure year/month
    """
    df = df.copy()

    # common rename guesses (edit if your headers differ)
    rename_map = {}
    if "amount" in df.columns and "budget_amount" not in df.columns:
        rename_map["amount"] = "budget_amount"
    if "Budget" in df.columns and "budget_amount" not in df.columns:
        rename_map["Budget"] = "budget_amount"
    if "Date" in df.columns and "date" not in df.columns:
        rename_map["Date"] = "date"
    df = df.rename(columns=rename_map)

    df = _ensure_period_cols(df)

    # keep only columns that exist in your bd template
    keep = [c for c in df.columns if c in bd_template.columns]
    df = df[keep]

    if "budget_amount" in df.columns:
        df["budget_amount"] = pd.to_numeric(df["budget_amount"], errors="coerce").fillna(0)

    return df

# Persist uploaded data across page switches
if "tx_user" not in st.session_state: st.session_state.tx_user = None
if "bd_user" not in st.session_state: st.session_state.bd_user = None

with st.sidebar.expander(" Upload monthly data", expanded=False):
    up_tx = st.file_uploader("Add transactions (01-like)", type=["xlsx", "xls", "csv"], key="u_tx")
    up_bd = st.file_uploader("Add budget (02-like)", type=["xlsx", "xls", "csv"], key="u_bd")
    mode = st.radio("How to apply", ["Append", "Replace"], horizontal=True, key="u_mode")

    if st.button("Apply uploads", type="primary", use_container_width=True):
        try:
            if up_tx is not None:
                tx_new = _read_any_table(up_tx)
                tx_new = _normalize_uploaded_tx(tx_new, tx)
                if mode == "Replace":
                    st.session_state.tx_user = tx_new
                else:
                    # Align columns then append
                    aligned_cols = [c for c in tx_new.columns if c in tx.columns]
                    tx_append = tx_new[aligned_cols]
                    st.session_state.tx_user = pd.concat(
                        [tx[aligned_cols], tx_append], ignore_index=True
                    )
            else:
                st.session_state.tx_user = None if mode == "Replace" else st.session_state.tx_user

            if up_bd is not None:
                bd_new = _read_any_table(up_bd)
                bd_new = _normalize_uploaded_budget(bd_new, bd)
                if mode == "Replace":
                    st.session_state.bd_user = bd_new
                else:
                    aligned_cols = [c for c in bd_new.columns if c in bd.columns]
                    bd_append = bd_new[aligned_cols]
                    st.session_state.bd_user = pd.concat(
                        [bd[aligned_cols], bd_append], ignore_index=True
                    )
            else:
                st.session_state.bd_user = None if mode == "Replace" else st.session_state.bd_user

            st.success("Data applied. All pages will reflect the new uploads.")
        except Exception as e:
            st.error(f"Upload failed: {e}")

# If we have uploaded replacements/appends, use them
if st.session_state.tx_user is not None:
    tx = st.session_state.tx_user
if st.session_state.bd_user is not None:
    bd = st.session_state.bd_user

# --------------------
# Sidebar: icon menu
# --------------------
with st.sidebar:
    st.markdown("### ")
    page = option_menu(
        menu_title=None,
        options=["Overview", "Revenue", "Expenses", "Table"],
        icons=["speedometer2", "bar-chart-line", "cash-coin", "table"],
        menu_icon="cast",
        default_index=0,
        styles={
            "container": {"padding": "0!important"},
            "icon": {"font-size": "18px"},
            "nav-link": {"font-size": "15px", "padding": "10px 8px"},
            "nav-link-selected": {"background-color": "#f0f2f6"},
        },
        orientation="vertical",
    )


# --------------------
# Global filters
# --------------------
if page == "Revenue":
    # Hide the global year selector on the Revenue page
    year = "All"
else:
    years = sorted(tx["year"].dropna().unique())
    colf1, colf2 = st.columns([1, 6])
    with colf1:
        year = st.selectbox("Year", options=["All"] + list(years), key="global_year")

DF = tx if year == "All" else tx[tx["year"].eq(int(year))]
MN = monthly_pnl(DF)  # builds monthly Revenue/COGS/OPEX + Gross Profit + EBIT

# =========================================================================
# OVERVIEW
# =========================================================================
if page == "Overview":
    st.title("Financial Performance — Overview")


    # --- Ensure year and month columns exist ---
    if "date" in DF.columns:
        DF["year"] = pd.to_datetime(DF["date"]).dt.year
        DF["month"] = pd.to_datetime(DF["date"]).dt.month

    if not bd.empty and "date" in bd.columns:
        bd["year"] = pd.to_datetime(bd["date"]).dt.year
        bd["month"] = pd.to_datetime(bd["date"]).dt.month

    # --- KPI calculations ---
    k = kpis(DF)  # from lib.metrics
    total_revenue = k["Revenue"]
    gross_profit = k["Gross Profit"]
    net_profit = k["EBIT"]
    cogs_val = DF.loc[DF["account_group"].eq("COGS"), "signed_amount"].sum()
    opex_val = DF.loc[DF["account_group"].eq("OPEX"), "signed_amount"].sum()

    # --- Budget Utilization (COGS only) ---
    actual_cogs_spend = abs(DF.loc[DF["account_group"].eq("COGS"), "signed_amount"].sum())

    if not bd.empty:
        total_budget_cogs = bd.loc[bd["account_group"].eq("COGS"), "budget_amount"].sum()
    else:
        total_budget_cogs = 0.0

    budget_util_pct = (actual_cogs_spend / total_budget_cogs * 100) if total_budget_cogs else 0.0

    # Margins & Ratios
    gp_margin = (gross_profit / total_revenue * 100) if total_revenue else 0
    np_margin = (net_profit / total_revenue * 100) if total_revenue else 0
    cogs_ratio = (cogs_val / total_revenue * 100) if total_revenue else 0
    opex_ratio = (opex_val / total_revenue * 100) if total_revenue else 0

    # Budget Utilization (% of total budget used by absolute actuals)
    if not bd.empty:
        total_budget = bd["budget_amount"].sum()
        budget_util = (abs(DF["signed_amount"].sum()) / total_budget * 100) if total_budget else 0
    else:
        budget_util = 0

    # --- KPI Cards Row (6 compact cards) ---
    # --- KPI Cards Row (spacious: 3 per row) ---
    kpi_style = """
    <style>
    .kpi-card { background:#f9fafb; border-radius:12px; padding:20px;
                box-shadow:0 2px 5px rgba(0,0,0,0.05); text-align:center; margin-bottom:20px; }
    .kpi-value { font-size:1.6rem; font-weight:700; }
    .kpi-sub   { font-size:0.9rem; }
    </style>
    """
    st.markdown(kpi_style, unsafe_allow_html=True)

    # Row 1
    c1, c2, c3 = st.columns(3)
    c1.markdown(kpi_card_md("Revenue", total_revenue, "green", f"▲ {gp_margin:.1f}% GP margin"), unsafe_allow_html=True)
    c2.markdown(kpi_card_md("Gross Profit", gross_profit, "#2563eb", f"{gp_margin:.1f}%"), unsafe_allow_html=True)
    c3.markdown(kpi_card_md("Net Profit", net_profit, "#6d28d9", f"{np_margin:.1f}%"), unsafe_allow_html=True)

    # Row 2
    c4, c5, c6 = st.columns(3)
    c4.markdown(kpi_card_md("COGS", cogs_val, "#ef4444", f"{cogs_ratio:.1f}% of Rev"), unsafe_allow_html=True)
    c5.markdown(kpi_card_md("OPEX", opex_val, "#f59e0b", f"{opex_ratio:.1f}% of Rev"), unsafe_allow_html=True)
    # Budget Utilization (COGS) card with % big + spend/budget details
    budget_card_html = f"""
    <div style="padding:12px;border-radius:12px;background:#f7f7fb;
                box-shadow:0 1px 4px rgba(0,0,0,0.08);text-align:center;">
      <div style="font-size:12px;color:#666;margin-bottom:4px;">Budget Utilization (COGS)</div>
      <div style="font-size:24px;font-weight:700;color:#0d9488;line-height:1;">
        {budget_util_pct:.1f}%
      </div>
      <div style="font-size:12px;color:#777;margin-top:4px;">
        Spend: ₦{actual_cogs_spend:,.0f} / Budget: ₦{total_budget_cogs:,.0f}
      </div>
    </div>
    """
    c6.markdown(budget_card_html, unsafe_allow_html=True)

    st.markdown("")  # spacing before charts

    # --- Revenue vs Budget (Monthly) ---
    # --- Revenue vs Expense (Yearly) ---
    st.subheader("Revenue vs Expense (Yearly)")

    rev_year = (
        DF[DF["account_group"].eq("Revenue")]
        .groupby("year", as_index=False)["signed_amount"].sum()
        .rename(columns={"signed_amount": "Revenue"})
    )

    exp_year = (
        DF[DF["account_group"].isin(["COGS", "OPEX"])]
        .groupby("year", as_index=False)["signed_amount"].sum()
        .rename(columns={"signed_amount": "Expenses"})
    )

    rev_exp = pd.merge(rev_year, exp_year, on="year", how="outer").fillna(0)

    fig_rev_exp = go.Figure()
    fig_rev_exp.add_bar(x=rev_exp["year"], y=rev_exp["Revenue"], name="Revenue")
    fig_rev_exp.add_bar(x=rev_exp["year"], y=rev_exp["Expenses"], name="Expenses")
    fig_rev_exp.update_layout(
        barmode="group",
        yaxis_title="₦",
        xaxis_title="Year",
        margin=dict(l=0, r=0, t=10, b=0)
    )
    st.plotly_chart(fig_rev_exp, use_container_width=True)

    # --- Expenses Breakdown (Monthly) ---
    st.subheader(" Expenses Breakdown (Monthly)")
    exp_month = (
        DF[DF["account_group"].isin(["COGS", "OPEX"])]
        .groupby(["year", "month", "account_group"], as_index=False)["signed_amount"].sum()
    )
    exp_month["Period"] = pd.to_datetime(dict(year=exp_month.year, month=exp_month.month, day=1))
    fig_exp = go.Figure()
    for grp in ["COGS", "OPEX"]:
        temp = exp_month[exp_month["account_group"] == grp]
        fig_exp.add_bar(x=temp["Period"], y=temp["signed_amount"], name=grp)
    fig_exp.update_layout(barmode="stack", yaxis_title="₦", xaxis_title="Month", margin=dict(l=0,r=0,t=10,b=0))
    st.plotly_chart(fig_exp, use_container_width=True)


    # --- Bottom Row: make the two left charts wider ---
    c1, c2, c3 = st.columns([1.6, 1.6, 1.0], gap="small")
    # ----- Better decision visuals -----
    # Current year (or filtered year) is already reflected in DF
    rev_df = DF[DF["account_group"].eq("Revenue")].copy()

    # Try to find a customer column
    cust_col = "NAME" if "NAME" in rev_df.columns else ("ACCOUNT" if "ACCOUNT" in rev_df.columns else None)

    with c1:
        st.subheader("Top 5 Customers & Concentration")

        if cust_col is None or rev_df[cust_col].nunique() == 0:
            st.info("No customer column found. Showing revenue trend instead.")
            # Fallback: simple monthly revenue trend
            if "month" in rev_df.columns and "year" in rev_df.columns:
                rev_df["Period"] = pd.to_datetime(dict(year=rev_df["year"], month=rev_df["month"], day=1))
                tr = rev_df.groupby("Period", as_index=False)["signed_amount"].sum()
                fig_tr = go.Figure()
                fig_tr.add_scatter(x=tr["Period"], y=tr["signed_amount"], mode="lines+markers", name="Revenue")
                fig_tr.update_layout(margin=dict(l=0, r=0, t=10, b=0), yaxis_title="₦")
                st.plotly_chart(fig_tr, use_container_width=True)
        else:
            rev_by_cust = (
                rev_df.groupby(cust_col, as_index=False)["signed_amount"]
                .sum()
                .sort_values("signed_amount", ascending=False)
            )
            top5 = rev_by_cust.head(5).copy()
            others = rev_by_cust["signed_amount"].iloc[5:].sum()
            total_rev = rev_by_cust["signed_amount"].sum() or 1
            top5_share = (top5["signed_amount"].sum() / total_rev) * 100

            # Horizontal bar for Top 5
            fig_top5 = go.Figure()
            fig_top5.add_bar(
                y=top5[cust_col][::-1],
                x=top5["signed_amount"][::-1],
                orientation="h",
                text=[f"₦{v:,.0f}" for v in top5["signed_amount"][::-1]],
                textposition="outside",
                name="Top 5 Customers"
            )
            fig_top5.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="₦",
                yaxis_title="Customer"
            )
            st.plotly_chart(fig_top5, use_container_width=True)

            st.caption(f" Top 5 customers = **{top5_share:.1f}%** of revenue. "
                       f"Others = ₦{others:,.0f}. "
                       f"If this % is high, revenue is concentrated (risk).")

    with c2:
        st.subheader("Top Cost Buckets")

        # Prefer Short_CLASS if available; else CLASS; else show Top Vendors
        bucket_col = "Short_CLASS" if "Short_CLASS" in DF.columns else ("CLASS" if "CLASS" in DF.columns else None)
        exp_df = DF[DF["account_group"].isin(["COGS", "OPEX"])].copy()
        exp_df["abs_amount"] = exp_df["signed_amount"].abs()

        if bucket_col:
            top_costs = (
                exp_df.groupby(bucket_col, as_index=False)["abs_amount"]
                .sum()
                .sort_values("abs_amount", ascending=False)
                .head(10)
            )
            fig_costs = go.Figure()
            fig_costs.add_bar(
                y=top_costs[bucket_col][::-1],
                x=top_costs["abs_amount"][::-1],
                orientation="h",
                text=[f"₦{v:,.0f}" for v in top_costs["abs_amount"][::-1]],
                textposition="outside",
                name="Cost Buckets"
            )
            fig_costs.update_layout(
                margin=dict(l=0, r=0, t=10, b=0),
                xaxis_title="₦",
                yaxis_title=bucket_col.replace("_", " ")
            )
            st.plotly_chart(fig_costs, use_container_width=True)
            st.caption(
                "💡 Largest buckets are your biggest levers. Investigate unit rates, vendor terms, and usage drivers.")
        else:
            vend_col = "NAME" if "NAME" in exp_df.columns else ("ACCOUNT" if "ACCOUNT" in exp_df.columns else None)
            if vend_col:
                top_vendors = (
                    exp_df.groupby(vend_col, as_index=False)["abs_amount"]
                    .sum()
                    .sort_values("abs_amount", ascending=False)
                    .head(10)
                )
                fig_vendors = go.Figure()
                fig_vendors.add_bar(
                    y=top_vendors[vend_col][::-1],
                    x=top_vendors["abs_amount"][::-1],
                    orientation="h",
                    text=[f"₦{v:,.0f}" for v in top_vendors["abs_amount"][::-1]],
                    textposition="outside",
                )
                fig_vendors.update_layout(
                    margin=dict(l=0, r=0, t=10, b=0),
                    xaxis_title="₦",
                    yaxis_title="Vendor"
                )
                st.plotly_chart(fig_vendors, use_container_width=True)
                st.caption(" Consider re‑bids or framework agreements for your top vendors.")
            else:
                st.info("No classification/vendor columns to break down expenses.")

# =========================================================================
# REVENUE
# =========================================================================

elif page == "Revenue":
    st.title("Revenue")

    # ---------- Local filters (year + month) ----------
    rev_all = DF[DF["account_group"].eq("Revenue")].copy()

    # Ensure year/month exist
    if "year" not in rev_all.columns and "date" in rev_all.columns:
        rev_all["year"] = pd.to_datetime(rev_all["date"]).dt.year
        rev_all["month"] = pd.to_datetime(rev_all["date"]).dt.month

    years_rev = sorted(rev_all["year"].dropna().unique())
    month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    months = list(range(1, 13))

    # Place before your revenue charts/tables
    f1, f2, _ = st.columns([1.5, 2.5, 3])  # Wider for month selector

    with f1:
        year_rev = st.selectbox(
            "Year",
            options=["All"] + list(years_rev),
            index=0,
            key="rev_year"
        )
    with f2:
        month_sel = st.multiselect(
            "Month",
            options=months,
            default=months,
            format_func=lambda m: month_names[m - 1],
            key="rev_months"
        )

    # Custom CSS for wider dropdown/multiselect
    st.markdown(
        """
        <style>
        div[data-baseweb="select"] {
            min-width: 250px;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

    # Apply filters
    R = rev_all.copy()
    if year_rev != "All":
        R = R[R["year"].eq(int(year_rev))]
    if month_sel:
        R = R[R["month"].isin(month_sel)]

    # ---------- KPIs ----------
    total_rev = R["signed_amount"].sum()

    # YoY growth (match same months last year)
    if year_rev != "All":
        prev_year = int(year_rev) - 1
        prev = rev_all[rev_all["year"].eq(prev_year)]
        if month_sel:
            prev = prev[prev["month"].isin(month_sel)]
        prev_sum = prev["signed_amount"].sum()
        yoy_pct = ((total_rev / prev_sum - 1.0) * 100) if prev_sum else 0.0
    else:
        yoy_pct = 0.0

    # Budget for the same slice (if provided)
    if not bd.empty:
        b = bd.copy()
        # make sure account_group and period columns exist
        if "year" not in b.columns and "date" in b.columns:
            b["year"] = pd.to_datetime(b["date"]).dt.year
        has_month = ("month" in b.columns) and b["month"].notna().any()

        b_rev = b[b["account_group"].eq("Revenue")].copy()
        if year_rev != "All":
            b_rev = b_rev[b_rev["year"].eq(int(year_rev))]
        if has_month:
            if month_sel:
                b_rev = b_rev[b_rev["month"].isin(month_sel)]
            budget_val = b_rev["budget_amount"].sum()
        else:
            # annual budgets only -> spread evenly across months in the filter
            months_in_slice = len(month_sel) if month_sel else 12
            ann = b_rev.groupby("year", as_index=False)["budget_amount"].sum()
            if year_rev == "All":
                budget_val = (ann["budget_amount"].sum() / 12.0) * months_in_slice
            else:
                budget_val = (ann["budget_amount"].sum() / 12.0) * months_in_slice
    else:
        budget_val = 0.0

    variance_val = total_rev - budget_val
    variance_pct = (variance_val / budget_val * 100) if budget_val else 0.0

    # KPI cards
    k1, k2, k3 = st.columns(3)
    k1.markdown(kpi_card_md("Total Revenue", total_rev, "#16a34a", ""), unsafe_allow_html=True)
    k2.markdown(kpi_card_md("YoY Change", total_rev, "#2563eb", f"{yoy_pct:+.1f}%"), unsafe_allow_html=True)
    k3.markdown(kpi_card_md("Vs Budget", variance_val, "#0ea5e9", f"{variance_pct:+.1f}%"), unsafe_allow_html=True)

    st.markdown("---")

    # ---------- Project-centric Revenue (uses ACCOUNT) ----------
    st.subheader("Project Revenue (Top 15)")

    # Pick the project column
    proj_col = None
    for c in ["ACCOUNT", "Account", "PROJECT", "Project"]:
        if c in R.columns:
            proj_col = c
            break

    if proj_col is None:
        st.info("No project column found (expected 'ACCOUNT' or 'PROJECT'). Showing monthly revenue instead.")
        # Simple monthly revenue bar (no prior-year overlay)
        tmp = (
            R.groupby(["year", "month"], as_index=False)["signed_amount"].sum()
            .rename(columns={"signed_amount": "Revenue"})
            .sort_values(["year", "month"])
        )
        tmp["Period"] = pd.to_datetime(dict(year=tmp["year"], month=tmp["month"], day=1))
        fig_simple = go.Figure()
        fig_simple.add_bar(x=tmp["Period"], y=tmp["Revenue"], name="Revenue")
        fig_simple.update_layout(margin=dict(l=0, r=0, t=10, b=0), yaxis_title="₦", xaxis_title="Month")
        st.plotly_chart(fig_simple, use_container_width=True)
    else:
        # 1) Leaderboard – Top projects in the current filter (year/month)
        by_proj = (
            R.groupby(proj_col, as_index=False)["signed_amount"].sum()
            .rename(columns={"signed_amount": "Revenue"})
            .sort_values("Revenue", ascending=False)
        )
        topN = by_proj.head(15)
        fig_lead = go.Figure()
        fig_lead.add_bar(
            y=topN[proj_col][::-1],
            x=topN["Revenue"][::-1],
            orientation="h",
            text=[f"₦{v:,.0f}" for v in topN["Revenue"][::-1]],
            textposition="outside",
            name="Projects"
        )
        fig_lead.update_layout(margin=dict(l=0, r=0, t=10, b=0), xaxis_title="₦", yaxis_title="Project")
        st.plotly_chart(fig_lead, use_container_width=True)

        # Concentration note (Top 5 share)
        total_slice = by_proj["Revenue"].sum() or 1
        top5_share = (by_proj["Revenue"].head(5).sum() / total_slice) * 100
        st.caption(f"🎯 Top 5 projects concentration: **{top5_share:.1f}%** of revenue.")

        st.markdown("---")

        # 2) Project picker → monthly trend for selected project
        # ---------- Simple Revenue Flow (Jan–Dec with Year selector) ----------
        st.subheader("Revenue Flow (Jan–Dec)")

        # Year dropdown just for this chart (unique key)
        flow_years = sorted(rev_all["year"].dropna().unique())
        flow_year = st.selectbox(
            "Year",
            options=flow_years,
            index=len(flow_years) - 1,  # default to latest year
            key="rev_flow_year"
        )

        # Build monthly series (ensure all 12 months exist)
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        base = (
            rev_all[rev_all["year"].eq(flow_year)]
            .groupby("month", as_index=False)["signed_amount"]
            .sum()
            .rename(columns={"signed_amount": "Revenue"})
        )

        full = (
            pd.DataFrame({"month": list(range(1, 13))})
            .merge(base, on="month", how="left")
            .fillna({"Revenue": 0})
        )
        full["MonthName"] = full["month"].map(lambda m: month_names[m - 1])
        full["Cumulative"] = full["Revenue"].cumsum()

        fig_flow = go.Figure()
        fig_flow.add_bar(x=full["MonthName"], y=full["Revenue"], name="Revenue")
        fig_flow.add_scatter(x=full["MonthName"], y=full["Cumulative"], mode="lines+markers", name="Cumulative")
        fig_flow.update_layout(
            margin=dict(l=0, r=0, t=10, b=0),
            yaxis_title="₦",
            xaxis_title="Month",
            barmode="group"
        )
        st.plotly_chart(fig_flow, use_container_width=True)

        # 3) Pivot view – Projects x Month for the current year
        # ---------- Projects × Month (pivot) ----------
        st.subheader("Projects × Month (pivot)")

        # Year selector just for this pivot (independent of other filters)
        pivot_years = sorted(rev_all["year"].dropna().unique())  # rev_all = all revenue rows (defined earlier)
        pivot_year = st.selectbox(
            "Year",
            options=pivot_years,
            index=len(pivot_years) - 1,  # default to latest year
            key="pivot_year"
        )

        # Filter the revenue slice to the chosen year
        base_y = R[R["year"].eq(pivot_year)].copy()  # R is your page-level filtered revenue

        # Top 20 projects for that year (keeps table readable)
        by_proj_y = (
            base_y.groupby(proj_col, as_index=False)["signed_amount"].sum()
            .rename(columns={"signed_amount": "Revenue"})
            .sort_values("Revenue", ascending=False)
        )
        keep = by_proj_y[proj_col].head(20).tolist()

        slice_small = base_y[base_y[proj_col].isin(keep)].copy()
        if "month" not in slice_small.columns or "year" not in slice_small.columns:
            st.info("Month/Year columns missing for pivot.")
        else:
            # Build pivot and make sure all 12 months show in order
            piv = slice_small.pivot_table(
                index=proj_col, columns="month", values="signed_amount",
                aggfunc="sum", fill_value=0
            )
            piv = piv.reindex(columns=range(1, 13), fill_value=0)  # ensure Jan..Dec columns exist
            # Keep same project order as leaderboard
            piv = piv.loc[keep]

            # Pretty month headers
            month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
            piv.columns = [month_names[m - 1] for m in piv.columns]

            st.dataframe(piv.style.format("₦{:,.0f}"), use_container_width=True)

    # ---------- Seasonality heatmap (Year × Month) ----------
    st.subheader("Seasonality Heatmap")
    heat = rev_all.groupby(["year","month"], as_index=False)["signed_amount"].sum()
    heat_p = heat.pivot_table(index="year", columns="month", values="signed_amount", aggfunc="sum", fill_value=0).sort_index()
    heat_p.columns = [month_names[m-1] for m in heat_p.columns]
    st.dataframe(heat_p.style.format("₦{:,.0f}").background_gradient(cmap="Blues"), use_container_width=True)


# =========================================================================
# EXPENSES
# =========================================================================
elif page == "Expenses":
    st.title("Expenses (₦)")

    # Ensure period columns
    if "year" not in DF.columns and "date" in DF.columns:
        DF["year"] = pd.to_datetime(DF["date"]).dt.year
        DF["month"] = pd.to_datetime(DF["date"]).dt.month

    # Choose a "project" field if available; else fall back gracefully
    project_col = "PROJECT" if "PROJECT" in DF.columns else ("NAME" if "NAME" in DF.columns else ("ACCOUNT" if "ACCOUNT" in DF.columns else None))
    if project_col is None:
        st.info("No 'PROJECT', 'NAME', or 'ACCOUNT' column found. Showing classification views only.")
    breakdown_default = "Project" if project_col else "Classification"

    # Controls
    leftc, rightc = st.columns([1,1])
    with leftc:
        granularity = st.radio("Granularity", ["Monthly", "Yearly"], horizontal=True)
    with rightc:
        breakdown = st.radio("Breakdown", ([breakdown_default] + ["Classification"]) if project_col else ["Classification"], horizontal=True)

    # Base expenses data
    EXP = DF[DF["account_group"].isin(["COGS", "OPEX"])].copy()
    EXP["abs_amount"] = EXP["signed_amount"].abs()

    # Totals KPI
    total_opex = EXP.loc[EXP["account_group"].eq("OPEX"), "abs_amount"].sum()
    total_cogs = EXP.loc[EXP["account_group"].eq("COGS"), "abs_amount"].sum()
    c1, c2 = st.columns(2)
    c1.markdown(kpi_card_md("OPEX (Total)", total_opex, "#f59e0b", ""), unsafe_allow_html=True)
    c2.markdown(kpi_card_md("COGS (Total)", total_cogs, "#ef4444", ""), unsafe_allow_html=True)

    st.markdown("---")

    # ---------- Time series: stacked COGS + OPEX ----------
    st.subheader("Expenses Over Time")
    if granularity == "Monthly":
        EXP["Period"] = pd.to_datetime(dict(year=EXP["year"], month=EXP["month"], day=1))
        grp = EXP.groupby(["Period", "account_group"], as_index=False)["abs_amount"].sum()
    else:  # Yearly
        grp = EXP.groupby(["year", "account_group"], as_index=False)["abs_amount"].sum()
        grp = grp.rename(columns={"year": "Period"})

    fig_exp = go.Figure()
    for grp_name in ["COGS", "OPEX"]:
        temp = grp[grp["account_group"] == grp_name]
        fig_exp.add_bar(x=temp["Period"], y=temp["abs_amount"], name=grp_name)
    fig_exp.update_layout(barmode="stack", yaxis_title="₦", xaxis_title="Period", margin=dict(l=0,r=0,t=10,b=0))
    st.plotly_chart(fig_exp, use_container_width=True)

    # ---------- Breakdown section ----------
    st.subheader("Expense Breakdown")

    if breakdown == "Project" and project_col:
        st.caption(f"By {project_col}")
        top_n = (
            EXP.groupby(project_col, as_index=False)["abs_amount"].sum()
            .sort_values("abs_amount", ascending=False)
            .head(15)
        )
        st.bar_chart(top_n.set_index(project_col)["abs_amount"])

        # Optional: table by project and month/year
        if granularity == "Monthly":
            piv = EXP.pivot_table(
                index=project_col,
                columns=["year", "month"],
                values="abs_amount",
                aggfunc="sum",
                fill_value=0
            )
            piv = piv.sort_values(by=piv.columns.tolist(), ascending=False)
        else:
            piv = EXP.pivot_table(
                index=project_col,
                columns="year",
                values="abs_amount",
                aggfunc="sum",
                fill_value=0
            )
            piv = piv.sort_values(by=piv.columns.tolist(), ascending=False)

    # Classification view (Chart of Accounts style)
    st.caption("By Classification (CLASS and Short_CLASS)")
    colA, colB = st.columns(2)
    with colA:
        st.markdown("**By CLASS**")
        by_class = EXP.groupby("CLASS", as_index=False)["abs_amount"].sum().sort_values("abs_amount", ascending=False)
        st.bar_chart(by_class.set_index("CLASS")["abs_amount"])
    with colB:
        st.markdown("**By Short_CLASS**")
        if "Short_CLASS" in EXP.columns:
            by_short = EXP.groupby("Short_CLASS", as_index=False)["abs_amount"].sum().sort_values("abs_amount", ascending=False)
            st.bar_chart(by_short.set_index("Short_CLASS")["abs_amount"])
        else:
            st.info("No Short_CLASS column found.")

    # Detail table: line items (filterable later if needed)
    # Detail table: line items (dedupe columns safely)
    # ------------------ Expense summary by line item (01's 4th column) ------------------
    st.markdown("---")
    st.subheader("Expense Summary by Line Item")

    # Pick the 4th-column / line-item field from 01.xlsx
    line_item_col = None
    for c in ["ACCOUNT", "Account", "PROJECT", "Project"]:
        if c in DF.columns:
            line_item_col = c
            break

    if line_item_col is None:
        st.info("Could not find the line-item column (e.g., 'ACCOUNT' or 'PROJECT') in 01 data.")
    else:
        # Make sure year/month are available
        if "year" not in DF.columns and "date" in DF.columns:
            DF["year"] = pd.to_datetime(DF["date"]).dt.year
            DF["month"] = pd.to_datetime(DF["date"]).dt.month

        # Work only with expenses (COGS + OPEX) and use absolute values for spend
        EXP = DF[DF["account_group"].isin(["COGS", "OPEX"])].copy()
        EXP["abs_amount"] = EXP["signed_amount"].abs()

        # ---- Filters (unique keys to avoid collisions) ----
        years_exp = sorted(EXP["year"].dropna().unique())
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
        months_all = list(range(1, 12 + 1))

        f1, f2, _ = st.columns([1.2, 2.2, 3])
        with f1:
            year_exp = st.selectbox("Year", options=["All"] + list(years_exp), index=0, key="exp_sum_year")
        with f2:
            month_exp = st.multiselect(
                "Month",
                options=months_all,
                default=months_all,
                format_func=lambda m: month_names[m - 1],
                key="exp_sum_months"
            )

        # Apply filters
        E = EXP.copy()
        if year_exp != "All":
            E = E[E["year"].eq(int(year_exp))]
        if month_exp:
            E = E[E["month"].isin(month_exp)]

        # Group by the line item (4th column) and sum spend
        summary = (
            E.groupby(line_item_col, as_index=False)["abs_amount"]
            .sum()
            .rename(columns={"abs_amount": "Amount"})
            .sort_values("Amount", ascending=False)
        )

        # Optional: show total on top
        total_spend = summary["Amount"].sum()
        st.caption(f"Total spend in selection: **₦{total_spend:,.0f}**")

        # Display table (no matplotlib dependency)
        st.dataframe(
            summary.style.format({"Amount": "₦{:,.0f}"}),
            use_container_width=True,
            hide_index=True
        )

        # (Optional) quick monthly pivot per line item — handy for spotting seasonality
        with st.expander("Monthly pivot by line item"):
            piv = (
                E.pivot_table(index=line_item_col, columns="month", values="abs_amount", aggfunc="sum", fill_value=0)
                .reindex(columns=months_all, fill_value=0)
            )
            piv.columns = [month_names[m - 1] for m in piv.columns]
            st.dataframe(
                piv.style.format("₦{:,.0f}"),
                use_container_width=True
            )



## =========================================================================
# STATEMENT OF PROFIT & LOSS (from 01.xlsx line items)
# =========================================================================
else:
    st.title("Statement of Profit & Loss ")

    # Ensure period columns exist
    if "year" not in DF.columns and "date" in DF.columns:
        DF["year"] = pd.to_datetime(DF["date"]).dt.year
        DF["month"] = pd.to_datetime(DF["date"]).dt.month

    # Controls: View (Year / Quarter / Month)
    colv, coly, colm = st.columns([1, 1, 1])
    with colv:
        gran = st.selectbox("View", ["Year", "Quarter", "Month"], index=0, key="pl_view")
    with coly:
        years_all = sorted(DF["year"].dropna().unique())
        sel_year = st.selectbox("Year", years_all, index=len(years_all)-1, key="pl_year")
    with colm:
        if gran == "Quarter":
            sel_q = st.selectbox("Quarter", ["Q1","Q2","Q3","Q4"], index=0, key="pl_quarter")
            sel_month = None
        elif gran == "Month":
            month_names = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
            m_idx = st.selectbox("Month", list(range(1,13)), format_func=lambda m: month_names[m-1], key="pl_month")
            sel_q = None
            sel_month = m_idx
        else:
            sel_q = None
            sel_month = None

    # Slice DF to the requested period
    def slice_period(df, year, granularity, q=None, m=None):
        df = df[df["year"].eq(int(year))].copy()
        if granularity == "Quarter" and q:
            qmap = {"Q1":[1,2,3], "Q2":[4,5,6], "Q3":[7,8,9], "Q4":[10,11,12]}
            df = df[df["month"].isin(qmap[q])]
        if granularity == "Month" and m:
            df = df[df["month"].eq(int(m))]
        return df

    S = slice_period(DF, sel_year, gran, sel_q, sel_month)

    # Helpers
    curr = "₦"
    def fmt(n): return f"{curr}{n:,.0f}"

    # Section builders (group by ACCOUNT within each account_group bucket)
    def section_rows(df, group_name):
        part = df[df["account_group"].eq(group_name)].copy()
        if part.empty:
            return [], 0.0
        by_line = (
            part.groupby("ACCOUNT", dropna=False, as_index=False)["signed_amount"]
                .sum()
                .sort_values("signed_amount", ascending=False)
        )
        rows = [(str(a if pd.notna(a) else "Unknown"), v) for a, v in zip(by_line["ACCOUNT"], by_line["signed_amount"])]
        subtotal = sum(v for _, v in rows)
        return rows, subtotal

    # Build sections
    rev_rows, rev_total = section_rows(S, "Revenue")
    cogs_rows, cogs_total = section_rows(S, "COGS")
    opex_rows, opex_total = section_rows(S, "OPEX")

    # Optional: detect "Other Income" if your chart uses a class/short class
    if "Short_CLASS" in S.columns:
        other_inc = S[S["Short_CLASS"].str.contains("other income", case=False, na=False)]
    elif "CLASS" in S.columns:
        other_inc = S[S["CLASS"].str.contains("other income", case=False, na=False)]
    else:
        other_inc = S[S["account_group"].eq("Other Income")] if "Other Income" in S.get("account_group", pd.Series([])).unique() else S.iloc[0:0]

    if not other_inc.empty:
        oi_rows = (
            other_inc.groupby("ACCOUNT", as_index=False)["signed_amount"]
            .sum()
            .sort_values("signed_amount", ascending=False)
        )
        other_rows = [(str(a if pd.notna(a) else "Unknown"), v) for a, v in zip(oi_rows["ACCOUNT"], oi_rows["signed_amount"])]
        other_total = sum(v for _, v in other_rows)
    else:
        other_rows, other_total = [], 0.0

    gross_profit = rev_total - cogs_total
    net_profit = gross_profit + other_total - opex_total

    # Period label
    if gran == "Year":
        period_label = f"For the year ended {sel_year}"
    elif gran == "Quarter":
        period_label = f"For the {sel_q} {sel_year}"
    else:
        mn = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][sel_month-1]
        period_label = f"For {mn} {sel_year}"

    st.caption(period_label)

    # Render HTML statement (clean, printable)
    def render_pl_html():
        def tr(label, val, bold=False, pad=False):
            style = "font-weight:700;" if bold else ""
            padl = "padding-left:18px;" if pad else ""
            amount = fmt(val) if (val is not None) else ""
            return f"""
            <tr>
              <td style="{padl}">{label}</td>
              <td style="text-align:right;{style}">{amount}</td>
            </tr>"""

        html = """
        <div style="
            background:#111827;border-radius:12px;padding:18px 18px 8px;
            border:1px solid #1f2937; color:#e5e7eb; font-size:15px;">
          <table style="width:100%; border-collapse:separate; border-spacing:0 6px;">
        """

        # Trading Income
        html += f'<tr><td colspan="2" style="font-weight:700; font-size:16px; color:#93c5fd;">Trading Income</td></tr>'
        if rev_rows:
            for lbl, val in rev_rows:
                html += tr(lbl, val, pad=True)
        else:
            html += tr("—", 0, pad=True)
        html += tr("Total Trading Income", rev_total, bold=True)

        # Cost of Sales
        html += f'<tr><td colspan="2" style="height:6px;"></td></tr>'
        html += f'<tr><td colspan="2" style="font-weight:700; font-size:16px; color:#93c5fd;">Cost of Sales</td></tr>'
        if cogs_rows:
            for lbl, val in cogs_rows:
                html += tr(lbl, val, pad=True)
        else:
            html += tr("—", 0, pad=True)
        html += tr("Total Cost of Sales", cogs_total, bold=True)

        # Gross Profit
        html += f'<tr><td colspan="2" style="height:6px;"></td></tr>'
        html += tr("Gross Profit", gross_profit, bold=True)

        # Other Income
        if other_rows:
            html += f'<tr><td colspan="2" style="height:6px;"></td></tr>'
            html += f'<tr><td colspan="2" style="font-weight:700; font-size:16px; color:#93c5fd;">Other Income</td></tr>'
            for lbl, val in other_rows:
                html += tr(lbl, val, pad=True)
            html += tr("Total Other Income", other_total, bold=True)

        # Operating Expenses
        html += f'<tr><td colspan="2" style="height:6px;"></td></tr>'
        html += f'<tr><td colspan="2" style="font-weight:700; font-size:16px; color:#93c5fd;">Operating Expenses</td></tr>'
        if opex_rows:
            for lbl, val in opex_rows:
                html += tr(lbl, val, pad=True)
        else:
            html += tr("—", 0, pad=True)
        html += tr("Total Operating Expenses", opex_total, bold=True)

        # Net Profit
        html += f'<tr><td colspan="2" style="height:8px;"></td></tr>'
        html += tr("Net Profit", net_profit, bold=True)

        html += "</table></div>"
        return html

    st.markdown(render_pl_html(), unsafe_allow_html=True)

    # -------- Export to Excel (same structure) --------
    def as_pl_dataframe():
        rows = []

        def add(label, val=None, header=False, pad=False):
            rows.append({
                "Line Item": (("    " if pad else "") + label) if not header else label,
                "Amount": val
            })

        add("Trading Income", header=True)
        if rev_rows:
            for lbl, val in rev_rows: add(lbl, val, pad=True)
        add("Total Trading Income", rev_total)

        add("")  # spacer
        add("Cost of Sales", header=True)
        if cogs_rows:
            for lbl, val in cogs_rows: add(lbl, val, pad=True)
        add("Total Cost of Sales", cogs_total)

        add("")  # spacer
        add("Gross Profit", gross_profit)

        if other_rows:
            add("")  # spacer
            add("Other Income", header=True)
            for lbl, val in other_rows: add(lbl, val, pad=True)
            add("Total Other Income", other_total)

        add("")  # spacer
        add("Operating Expenses", header=True)
        if opex_rows:
            for lbl, val in opex_rows: add(lbl, val, pad=True)
        add("Total Operating Expenses", opex_total)

        add("")  # spacer
        add("Net Profit", net_profit)

        df_out = pd.DataFrame(rows)
        return df_out

    pl_df = as_pl_dataframe()

    # Show a compact dataframe view (optional)
    with st.expander("Show table view"):
        st.dataframe(
            pl_df.style.format({"Amount": "₦{:,.0f}"}),
            use_container_width=True
        )

    # Download Excel
    def to_excel_bytes(df):
        buf = io.BytesIO()
        with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
            df.to_excel(writer, index=False, sheet_name="P&L")
        buf.seek(0)
        return buf

    st.download_button(
        "⬇️ Download P&L (Excel)",
        data=to_excel_bytes(pl_df),
        file_name=f"Statement_of_PL_{gran}_{sel_year}.xlsx",
        type="primary"
    )
