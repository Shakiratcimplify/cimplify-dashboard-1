import base64
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

def kpi_card_md(label, value, color="black", trend_text=""):
    """
    HTML KPI card for Streamlit.
    - label: title of KPI
    - value: numeric (formatted with ₦)
    - color: CSS color for the value text
    - trend_text: e.g., '▲ 5.2%' or '▼ 1.1%'
    """
    try:
        value_fmt = f"₦{float(value):,.0f}"
    except Exception:
        value_fmt = str(value)

    trend_color = "green" if ("▲" in trend_text or "+" in trend_text) else ("red" if ("▼" in trend_text or "-" in trend_text) else "#777")

    html = f"""
    <div style="padding:12px;border-radius:12px;background:#f7f7fb;box-shadow:0 1px 4px rgba(0,0,0,0.08);text-align:center;">
        <div style="font-size:12px;color:#666;margin-bottom:4px;">{label}</div>
        <div style="font-size:24px;font-weight:700;color:{color};line-height:1;">{value_fmt}</div>
        <div style="font-size:12px;color:{trend_color};margin-top:4px;">{trend_text}</div>
    </div>
    """
    return html

def donut(df, group_col, value_col="signed_amount", title=""):
    s = df.groupby(group_col, as_index=False)[value_col].sum().sort_values(value_col, ascending=False)
    fig = px.pie(s, names=group_col, values=value_col, hole=0.6, title=title)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(margin=dict(l=0, r=0, t=40, b=0))
    return fig

def line_two(df, x, y1, y2, title=""):
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df[x], y=df[y1], mode="lines+markers", name=y1))
    fig.add_trace(go.Scatter(x=df[x], y=df[y2], mode="lines+markers", name=y2))
    fig.update_layout(title=title, xaxis_title="", yaxis_title="", margin=dict(l=0, r=0, t=40, b=0))
    return fig

def waterfall_from_monthly(df, title="Net Profit/Loss by Month"):
    df = df.copy()
    df["period"] = pd.to_datetime(dict(year=df["year"], month=df["month"], day=1))
    df = df.sort_values("period")
    fig = go.Figure(go.Waterfall(
        x=df["period"].dt.strftime("%b"),
        y=df["EBIT"],
        measure=["relative"] * len(df),
        connector={"line": {"width": 1}}
    ))
    fig.update_layout(title=title, margin=dict(l=0, r=0, t=40, b=0))
    return fig

def inject_watermark(st, image_path="assets/logo.png", opacity=0.06):
    try:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        css = f"""
        <style>
        .stApp::before {{
            content: "";
            position: fixed;
            top: 0; left: 0; width: 100%; height: 100%;
            background-image: url("data:image/png;base64,{b64}");
            background-size: 50%;
            background-repeat: no-repeat;
            background-position: right 5% bottom 5%;
            opacity: {opacity};
            pointer-events: none;
            z-index: -1;
        }}
        </style>
        """
        st.markdown(css, unsafe_allow_html=True)
    except Exception:
        pass
