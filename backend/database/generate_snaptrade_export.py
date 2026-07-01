"""
generate_snaptrade_export.py
────────────────────────────
Fetches all data for a SnapTrade user and writes snaptrade_full_export.json
in the format expected by your existing loader scripts.

Requirements:
    pip install snaptrade-python-sdk
"""

import json
import os
from datetime import datetime, timezone
from snaptrade_client import SnapTrade

# ── Credentials ───────────────────────────────────────────────────────────────
CLIENT_ID      = "BFI-DFTUD"               # your SnapTrade client ID
CONSUMER_KEY   = "UflJTFaCJXSpEEmoGaEjtotESLszJnvFlXrglda7xlWRbAgb6y"  # from SnapTrade dashboard
USERNAME       = "cgschwarz0424"
USER_SECRET    = "a05ea687-dac6-4124-907b-04884753105b"

OUTPUT_FILE    = "data-export/snaptrade_full_export.json"

# ── Init client ───────────────────────────────────────────────────────────────
snaptrade = SnapTrade(
    client_id=CLIENT_ID,
    consumer_key=CONSUMER_KEY,
)

def safe_json(obj):
    """Convert SDK response objects to plain dicts/lists recursively."""
    if hasattr(obj, "to_dict"):
        return safe_json(obj.to_dict())
    if isinstance(obj, dict):
        return {k: safe_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [safe_json(i) for i in obj]
    return obj

print(f"Fetching accounts for user: {USERNAME}")

# ── Fetch all brokerage accounts ──────────────────────────────────────────────
accounts_resp = snaptrade.account_information.list_user_accounts(
    user_id=USERNAME,
    user_secret=USER_SECRET,
)
accounts_list = safe_json(accounts_resp.body) or []

export_accounts = []

for account in accounts_list:
    account_id = account.get("id")
    print(f"  → Processing account: {account.get('name')} ({account_id})")

    # ── Balances ──────────────────────────────────────────────────────────────
    try:
        balances_resp = snaptrade.account_information.get_user_account_balance(
            user_id=USERNAME,
            user_secret=USER_SECRET,
            account_id=account_id,
        )
        balances = safe_json(balances_resp.body) or []
    except Exception as e:
        print(f"    ⚠️  Balances failed: {e}")
        balances = []

    # ── Positions ─────────────────────────────────────────────────────────────
    try:
        positions_resp = snaptrade.account_information.get_user_account_positions(
            user_id=USERNAME,
            user_secret=USER_SECRET,
            account_id=account_id,
        )
        positions = safe_json(positions_resp.body) or []
    except Exception as e:
        print(f"    ⚠️  Positions failed: {e}")
        positions = []

    # ── Orders ────────────────────────────────────────────────────────────────
    try:
        orders_resp = snaptrade.account_information.get_user_account_orders(
            user_id=USERNAME,
            user_secret=USER_SECRET,
            account_id=account_id,
        )
        orders = safe_json(orders_resp.body) or []
    except Exception as e:
        print(f"    ⚠️  Orders failed: {e}")
        orders = []

    # ── Activities / Transactions ─────────────────────────────────────────────
    try:
        activities_resp = snaptrade.transactions_and_reporting.get_activities(
            user_id=USERNAME,
            user_secret=USER_SECRET,
            accounts=account_id,   # filter to this account
        )
        activities_raw = safe_json(activities_resp.body) or []
        # Wrap in the {data: [...]} envelope your loader expects
        activities = {"data": activities_raw}
    except Exception as e:
        print(f"    ⚠️  Activities failed: {e}")
        activities = {"data": []}

    export_accounts.append({
        "account":    account,
        "balances":   balances if isinstance(balances, list) else [balances],
        "positions":  positions,
        "orders":     orders,
        "activities": activities,
    })

# ── Write output ──────────────────────────────────────────────────────────────
os.makedirs("data-export", exist_ok=True)

export = {
    "exported_at": datetime.now(timezone.utc).isoformat(),
    "accounts": export_accounts,
}

with open(OUTPUT_FILE, "w") as f:
    json.dump(export, f, indent=2, default=str)

print(f"\n✅ Export written to {OUTPUT_FILE}")
print(f"   Accounts:  {len(export_accounts)}")
print(f"   Positions: {sum(len(a['positions']) for a in export_accounts)}")
print(f"   Orders:    {sum(len(a['orders']) for a in export_accounts)}")
print(f"   Activities:{sum(len(a['activities']['data']) for a in export_accounts)}")