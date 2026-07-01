import json
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
import uuid
import os

# ── Config ────────────────────────────────
DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://snaptrade_user:testing@localhost:5432/snaptrade_db"
)
EXPORT_FILE = "data-export/snaptrade_full_export.json"


# ── Helpers ───────────────────────────────
def parse_dt(val):
    if not val:
        return None
    try:
        return datetime.fromisoformat(str(val).replace("Z", "+00:00"))
    except:
        return None

def safe_dict(x):
    return x if isinstance(x, dict) else {}

def safe_currency(obj):
    return obj.get("code") if isinstance(obj, dict) else None

def is_uuid(val):
    try:
        uuid.UUID(str(val))
        return True
    except:
        return False

def extract_symbol(obj):
    if not obj:
        return None
    if isinstance(obj, str):
        return None if is_uuid(obj) else obj
    if isinstance(obj, dict):
        for key in ["symbol", "raw_symbol", "ticker"]:
            val = obj.get(key)
            if isinstance(val, str) and not is_uuid(val):
                return val
        inner = obj.get("symbol")
        if isinstance(inner, dict):
            val = inner.get("symbol") or inner.get("raw_symbol")
            if val and not is_uuid(val):
                return val
    return None

def ensure_uuid(series):
    return series.apply(lambda x: x if pd.notnull(x) and str(x).strip() != "" else str(uuid.uuid4()))


# ── Main callable ─────────────────────────
def sync_export_to_db(export_file: str = EXPORT_FILE, db_url: str = DB_URL, verbose: bool = False) -> dict:
    """
    Parse snaptrade_full_export.json and upsert into PostgreSQL.
    Returns a stats dict: {accounts, positions, orders, transactions}.
    """
    if not os.path.exists(export_file):
        raise FileNotFoundError(f"Export file not found: {export_file}")

    with open(export_file) as f:
        data = json.load(f)

    accounts_rows = []
    positions_rows = []
    orders_rows = []
    transactions_rows = []

    for acc_wrapper in data.get("accounts", []):
        account = safe_dict(acc_wrapper.get("account"))
        balances_list = acc_wrapper.get("balances") or [{}]
        balances = balances_list[0] if isinstance(balances_list, list) else balances_list
        balances = safe_dict(balances)

        account_id = account.get("id") or str(uuid.uuid4())

        # ── Accounts ──────────────────────────
        accounts_rows.append({
            "id": account_id,
            "username": "default_user",
            "name": account.get("name"),
            "number": account.get("number"),
            "institution_name": account.get("institution_name"),
            "account_type": safe_dict(account.get("meta")).get("type"),
            "status": safe_dict(account.get("meta")).get("accountStatus"),
            "is_paper": False,
            "currency": safe_currency(balances.get("currency")),
            "total_balance": balances.get("amount"),
            "cash": balances.get("cash"),
            "buying_power": balances.get("buying_power"),
            "created_date": parse_dt(account.get("created_date")),
            "last_synced": parse_dt(
                safe_dict(account.get("sync_status"))
                .get("holdings", {})
                .get("last_successful_sync")
            ),
        })

        # ── Positions ─────────────────────────
        for pos in acc_wrapper.get("positions", []):
            symbol = extract_symbol(pos.get("symbol"))
            if not symbol:
                continue

            units = pos.get("units") or 0
            price = pos.get("price") or 0
            avg = pos.get("average_purchase_price") or 0

            positions_rows.append({
                "account_id": account_id,
                "symbol": symbol,
                "description": safe_dict(pos.get("symbol")).get("description"),
                "units": units,
                "price": price,
                "average_purchase_price": avg,
                "open_pnl": pos.get("open_pnl"),
                "market_value": units * price,
                "cost_basis": units * avg,
                "is_cash_equivalent": False,
            })

        # ── Transactions ──────────────────────
        activities = acc_wrapper.get("activities", {})

        for txn in (activities.get("data", []) if isinstance(activities, dict) else []):
            sym_obj = txn.get("symbol") or {}
            symbol = (sym_obj.get("symbol") or sym_obj.get("raw_symbol")) if isinstance(sym_obj, dict) else None

            transactions_rows.append({
                "id":              txn.get("id"),
                "account_id":      account_id,
                "symbol":          symbol,
                "type":            txn.get("type"),
                "action":          txn.get("option_type"),
                "description":     txn.get("description"),
                "amount":          txn.get("amount"),
                "price":           txn.get("price"),
                "units":           abs(txn.get("units") or 0),
                "fee":             txn.get("fee"),
                "currency":        safe_dict(txn.get("currency")).get("code"),
                "trade_date":      parse_dt(txn.get("trade_date")),
                "settlement_date": parse_dt(txn.get("settlement_date")),
                "institution":     txn.get("institution"),
            })

        # ── Orders ────────────────────────────
        for order in acc_wrapper.get("orders", []):
            order_id = order.get("brokerage_order_id") or order.get("id")

            uni = order.get("universal_symbol") or {}
            if isinstance(uni, dict):
                underlying_symbol = uni.get("symbol") or uni.get("raw_symbol")
            else:
                underlying_symbol = extract_symbol(order.get("symbol"))

            orders_rows.append({
                "id":                 order_id,
                "account_id":         account_id,
                "status":             order.get("status"),
                "action":             order.get("action"),
                "order_type":         order.get("order_type"),
                "underlying_symbol":  underlying_symbol,
                "total_quantity":     float(order.get("total_quantity") or 0),
                "filled_quantity":    float(order.get("filled_quantity") or 0),
                "execution_price":    float(order.get("execution_price") or 0),
                "time_placed":        parse_dt(order.get("time_placed")),
                "time_executed":      parse_dt(order.get("time_executed")),
            })

    # ── Convert to DataFrames ─────────────────
    df_accounts     = pd.DataFrame(accounts_rows)
    df_positions    = pd.DataFrame(positions_rows)
    df_orders       = pd.DataFrame(orders_rows)
    df_transactions = pd.DataFrame(transactions_rows)

    # ── Ensure IDs exist ──────────────────────
    if not df_orders.empty:
        df_orders["id"] = ensure_uuid(df_orders["id"]).astype(str)

    if not df_transactions.empty:
        df_transactions["id"] = ensure_uuid(df_transactions["id"]).astype(str)

    # ── Write to DB ───────────────────────────
    engine = create_engine(db_url)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM transactions;"))
        conn.execute(text("DELETE FROM orders;"))
        conn.execute(text("DELETE FROM positions;"))
        conn.execute(text("DELETE FROM accounts;"))

        if not df_accounts.empty:
            df_accounts.to_sql("accounts", engine, if_exists="append", index=False)
        if not df_positions.empty:
            df_positions.to_sql("positions", engine, if_exists="append", index=False)
        if not df_orders.empty:
            df_orders.to_sql("orders", engine, if_exists="append", index=False)
        if not df_transactions.empty:
            df_transactions.to_sql("transactions", engine, if_exists="append", index=False)

    stats = {
        "accounts":     len(df_accounts),
        "positions":    len(df_positions),
        "orders":       len(df_orders),
        "transactions": len(df_transactions),
    }

    if verbose:
        print(f"✅ DB sync complete!")
        for k, v in stats.items():
            print(f"  {k.capitalize()}: {v}")

    return stats


# ── Allow running as a standalone script too ──
if __name__ == "__main__":
    sync_export_to_db(verbose=True)