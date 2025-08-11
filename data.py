import pandas as pd
import numpy as np
from pathlib import Path

TXN_FILE = "01.xlsx"
BUDGET_FILE = "02_budget.xlsx"

def _norm_cols(df):
    df = df.copy()
    df.columns = [str(c).strip() for c in df.columns]
    return df

def _infer_group(row):
    side = str(row.get("REVENUE/EXPENSES", "")).strip().lower()
    short = str(row.get("Short_CLASS", "")).strip().upper()
    full = str(row.get("CLASS", "")).strip().lower()

    if side == "revenue":
        return "Revenue"
    if side == "expenses":
        # Prefer Short_CLASS if present
        if short == "COS":
            return "COGS"
        if short in ("G&A", "GA", "GNA"):
            return "OPEX"
        # Fallback to CLASS text
        if full.startswith("cost of sales"):
            return "COGS"
        if "general & administrative" in full or "general and administrative" in full:
            return "OPEX"
    return None  # ignore anything else (assets/liab/etc.)

def load_all(txn_path=TXN_FILE, budget_path=BUDGET_FILE):
    # ---- Load transactions
    tx = pd.read_excel(txn_path)
    tx = _norm_cols(tx)

    # Required
    if "Date" not in tx.columns or "AMOUNT" not in tx.columns or "REVENUE/EXPENSES" not in tx.columns:
        raise ValueError("01.xlsx must contain 'Date', 'AMOUNT', and 'REVENUE/EXPENSES' columns.")

    # Derive period + account_group
    tx["date"] = pd.to_datetime(tx["Date"], errors="coerce")
    tx["year"] = tx["date"].dt.year
    tx["month"] = tx["date"].dt.month

    # Keep originals but add our normalized helpers
    if "Short_CLASS" not in tx.columns:
        tx["Short_CLASS"] = ""
    if "CLASS" not in tx.columns:
        tx["CLASS"] = ""

    tx["account_group"] = tx.apply(_infer_group, axis=1)

    # Signed amounts: Revenue +, COGS/OPEX −, drop non-P&L
    def sign_amt(row):
        grp = row["account_group"]
        amt = row["AMOUNT"]
        if grp == "Revenue":
            return abs(amt)
        if grp in ("COGS", "OPEX"):
            return -abs(amt)
        return np.nan

    tx["signed_amount"] = tx.apply(sign_amt, axis=1)
    tx = tx.dropna(subset=["signed_amount"])

    # ---- Load & prepare budget if present (optional)
    bd = pd.DataFrame(columns=["year", "account_group", "budget_amount"])
    if Path(budget_path).exists():
        b = pd.read_excel(budget_path)
        b = _norm_cols(b)
        if "DATE" in b.columns:
            b["date"] = pd.to_datetime(b["DATE"], errors="coerce")
        elif "Date" in b.columns:
            b["date"] = pd.to_datetime(b["Date"], errors="coerce")
        else:
            b["date"] = pd.NaT
        b["year"] = b["date"].dt.year

        # Build account_group from same rules (Revenue/Expenses + Short_CLASS/CLASS)
        if "REVENUE/EXPENSES" not in b.columns:
            b["REVENUE/EXPENSES"] = ""
        if "Short_CLASS" not in b.columns:
            b["Short_CLASS"] = ""
        if "CLASS" not in b.columns:
            b["CLASS"] = ""
        b["account_group"] = b.apply(_infer_group, axis=1)

        # Budget amount column
        bud_col = "BUDGET" if "BUDGET" in b.columns else "budget_amount"
        if bud_col not in b.columns:
            b[bud_col] = 0.0

        b = b.dropna(subset=["account_group"])
        bd = b.groupby(["year", "account_group"], as_index=False)[bud_col].sum()
        bd = bd.rename(columns={bud_col: "budget_amount"})

    return tx, bd
