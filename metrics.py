import pandas as pd

def kpis(df):
    rev = df.loc[df["account_group"].eq("Revenue"), "signed_amount"].sum()
    cogs = df.loc[df["account_group"].eq("COGS"), "signed_amount"].sum()
    opex = df.loc[df["account_group"].eq("OPEX"), "signed_amount"].sum()
    gross_profit = rev + cogs
    ebit = gross_profit + opex
    return {"Revenue": rev, "Gross Profit": gross_profit, "EBIT": ebit}

def monthly_pnl(df):
    g = df.groupby(["year", "month", "account_group"], as_index=False)["signed_amount"].sum()
    pivot = g.pivot_table(index=["year","month"], columns="account_group", values="signed_amount", fill_value=0).reset_index()
    for col in ("Revenue","COGS","OPEX"):
        if col not in pivot.columns: pivot[col] = 0
    pivot["Gross Profit"] = pivot["Revenue"] + pivot["COGS"]
    pivot["EBIT"] = pivot["Gross Profit"] + pivot["OPEX"]
    return pivot
