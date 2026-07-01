import json
import pandas as pd
from sqlalchemy import create_engine, text

# ── DB Connection ──────────────────────────
engine = create_engine(
    "postgresql+psycopg2://snaptrade_user:testing@localhost:5432/snaptrade_db"
)

# ── Helpers ────────────────────────────────
def safe_dict(obj):
    return obj if isinstance(obj, dict) else {}

def get_symbol(obj):
    if isinstance(obj, dict):
        return obj.get("symbol")
    if isinstance(obj, str):
        return obj
    return None

# ── Reset Tables ───────────────────────────
with engine.begin() as conn:
    conn.execute(text("DELETE FROM transactions;"))
    conn.execute(text("DELETE FROM orders;"))
    conn.execute(text("DELETE FROM positions;"))
    conn.execute(text("DELETE FROM accounts;"))

# ── Load JSON ──────────────────────────────
with open("data-export/snaptrade_full_export.json") as f:
    data = json.load(f)

accounts_data = []
positions_data = []
transactions_data = []
orders_data = []

# ── Parse Data ─────────────────────────────
for acc_wrapper in data.get("accounts", []):

    account = safe_dict(acc_wrapper.get("account"))
    balances_list = acc_wrapper.get("balances") or [{}]
    balances = balances_list[0] if isinstance(balances_list, list) else balances_list
    balances = safe_dict(balances)

    account_id = account.get("id")

    # ── ACCOUNTS ───────────────────────────
    accounts_data.append({
        "id": account_id,
        "username": "default_user",
        "name": account.get("name"),
        "number": account.get("number"),
        "institution_name": account.get("institution_name"),
        "account_type": safe_dict(account.get("meta")).get("type"),
        "status": safe_dict(account.get("meta")).get("accountStatus"),
        "is_paper": False,
        "currency": safe_dict(balances.get("currency")).get("code"),
        "total_balance": balances.get("amount"),
        "cash": balances.get("cash"),
        "buying_power": balances.get("buying_power"),
        "created_date": account.get("created_date"),
        "last_synced": safe_dict(account.get("sync_status"))
                        .get("holdings", {})
                        .get("last_successful_sync"),
    })

    # ── POSITIONS ──────────────────────────
    for pos in acc_wrapper.get("positions", []):
        symbol_obj = pos.get("symbol")

        if isinstance(symbol_obj, dict):
            symbol = symbol_obj.get("symbol")
        elif isinstance(symbol_obj, str):
            symbol = symbol_obj
        else:
            symbol = None

        if not symbol:
            print("⚠️ Skipping position (no symbol):", pos)
            continue

        units = pos.get("units") or 0
        price = pos.get("price") or 0
        avg_price = pos.get("average_purchase_price") or 0

        positions_data.append({
            "account_id": account_id,
            "symbol": symbol,
            "description": symbol_obj.get("description") if isinstance(symbol_obj, dict) else None,
            "exchange": symbol_obj.get("exchange", {}).get("code") if isinstance(symbol_obj, dict) else None,
            "asset_type": symbol_obj.get("type", {}).get("name") if isinstance(symbol_obj, dict) else None,
            "currency": symbol_obj.get("currency", {}).get("code") if isinstance(symbol_obj, dict) else None,
            "units": units,
            "price": price,
            "average_purchase_price": avg_price,
            "open_pnl": pos.get("open_pnl"),
            "market_value": units * price,
            "cost_basis": units * avg_price,
            "is_cash_equivalent": False,
        })

    # ── TRANSACTIONS ───────────────────────
    activities = safe_dict(acc_wrapper.get("activities"))

    for txn in activities.get("data", []):
        symbol_obj = txn.get("symbol")
        option_symbol = safe_dict(txn.get("option_symbol"))

        if isinstance(symbol_obj, dict):
            symbol = symbol_obj.get("symbol")
        elif isinstance(symbol_obj, str):
            symbol = symbol_obj
        else:
            symbol = None

        transactions_data.append({
            "id": txn.get("id"),
            "account_id": account_id,
            "symbol": symbol,
            "option_ticker": option_symbol.get("ticker"),
            "type": txn.get("type"),
            "action": txn.get("option_type"),
            "description": txn.get("description"),
            "amount": txn.get("amount"),
            "price": txn.get("price"),
            "units": txn.get("units"),
            "fee": txn.get("fee"),
            "currency": safe_dict(txn.get("currency")).get("code"),
            "trade_date": txn.get("trade_date"),
            "settlement_date": txn.get("settlement_date"),
            "institution": txn.get("institution"),
        })

    # ── ORDERS ─────────────────────────────
    for order in acc_wrapper.get("orders", []):
        symbol_obj = order.get("symbol")

        if isinstance(symbol_obj, dict):
            underlying_symbol = symbol_obj.get("symbol")
        elif isinstance(symbol_obj, str):
            underlying_symbol = symbol_obj
        else:
            underlying_symbol = None

        orders_data.append({
            "id": order.get("id"),
            "account_id": account_id,
            "status": order.get("status"),
            "action": order.get("action"),
            "order_type": order.get("order_type"),
            "underlying_symbol": underlying_symbol,
            "total_quantity": order.get("units"),
            "filled_quantity": order.get("filled_units"),
            "execution_price": order.get("execution_price"),
            "time_placed": order.get("time_placed"),
        })

# ── Write to DB ────────────────────────────
pd.DataFrame(accounts_data).to_sql("accounts", engine, if_exists="append", index=False)

if positions_data:
    pd.DataFrame(positions_data).to_sql("positions", engine, if_exists="append", index=False)

if transactions_data:
    pd.DataFrame(transactions_data).to_sql("transactions", engine, if_exists="append", index=False)

if orders_data:
    pd.DataFrame(orders_data).to_sql("orders", engine, if_exists="append", index=False)

print("✅ Full SnapTrade export loaded successfully!")