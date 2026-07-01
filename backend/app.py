from flask import Flask, jsonify, request, session, Response
from flask_cors import CORS
from functools import wraps
import os
from datetime import datetime, timedelta
from snaptrade_client import SnapTrade
import json
import yfinance as yf
import logging
import hashlib
import secrets
import requests
from requests.adapters import HTTPAdapter
import re
import glob

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True, origins=['http://localhost:3000', 'http://localhost:3001', 'http://127.0.0.1:3000', 'http://127.0.0.1:3001', 'http://18.221.160.103:5001', 'http://18.221.160.103:3000', 'http://bfi.duckdns.org'])

# Configuration
SNAPTRADE_CLIENT_ID = "BFI-DFTUD"
SNAPTRADE_CONSUMER_KEY = "UflJTFaCJXSpEEmoGaEjtotESLszJnvFlXrglda7xlWRbAgb6y"


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Basic Auth for the internal SnapTrade data platform (/api/explorer/*,
# /api/db/*). This is a lightweight shared-credentials gate for the creators-only
# data explorer — NOT the user-facing dashboard, which uses session auth.
# Override the defaults via env vars EXPLORER_USER / EXPLORER_PASS.
# ─────────────────────────────────────────────────────────────────────────────
EXPLORER_USER = os.environ.get('EXPLORER_USER', 'admin')
EXPLORER_PASS = os.environ.get('EXPLORER_PASS', 'changeme')


def require_basic_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or auth.username != EXPLORER_USER or auth.password != EXPLORER_PASS:
            return Response(
                'Authentication required.', 401,
                {'WWW-Authenticate': 'Basic realm="SnapTrade Data Platform"'}
            )
        return f(*args, **kwargs)
    return decorated


# Database files
USERS_DB_FILE = 'users.json'
ACCOUNT_DATA_DIR = 'data-export'
ACCOUNT_DATA_FILE = os.path.join(ACCOUNT_DATA_DIR, 'account-data.json')


from models import db, User, Account, Position, Order, Activity
from db_sync import sync_export_to_db

# PostgreSQL: set DATABASE_URL=postgresql+psycopg://user:pass@localhost/dbname
# Local dev default uses SQLite (no Postgres install required).
_default_db_path = os.path.join(os.path.dirname(__file__), 'portfolio.db')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    f'sqlite:///{_default_db_path}'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# Create tables on startup
with app.app_context():
    db.create_all()

# Ensure data-export directory exists
os.makedirs(ACCOUNT_DATA_DIR, exist_ok=True)

def load_users():
    """Load users from JSON file"""
    if os.path.exists(USERS_DB_FILE):
        try:
            with open(USERS_DB_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_users(users):
    """Save users to JSON file"""
    with open(USERS_DB_FILE, 'w') as f:
        json.dump(users, f, indent=2)

def load_account_data():
    """Load account data from JSON file"""
    if os.path.exists(ACCOUNT_DATA_FILE):
        try:
            with open(ACCOUNT_DATA_FILE, 'r') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_account_data(account_data):
    """Save account data to JSON file"""
    with open(ACCOUNT_DATA_FILE, 'w') as f:
        json.dump(account_data, f, indent=2)

def hash_password(password):
    """Hash password using SHA256"""
    return hashlib.sha256(password.encode()).hexdigest()

def get_current_user():
    """Get current logged-in user from session"""
    if 'username' in session:
        users = load_users()
        return users.get(session['username'])
    return None

def get_snaptrade_client():
    """Get SnapTrade client with global credentials"""
    return SnapTrade(
        client_id=SNAPTRADE_CLIENT_ID,
        consumer_key=SNAPTRADE_CONSUMER_KEY
    )

def get_user_credentials():
    """Get user credentials for current user"""
    user = get_current_user()
    if user:
        return user.get('snaptrade_user_id'), user.get('snaptrade_user_secret')
    return None, None


def _symbol_from_activity(activity):
    raw = activity.get('symbol')
    if isinstance(raw, dict):
        inner = raw.get('symbol')
        if isinstance(inner, dict):
            return inner.get('symbol') or inner.get('raw_symbol')
        return inner or raw.get('raw_symbol')
    return raw


def _description_from_activity(activity, symbol):
    raw = activity.get('symbol')
    if isinstance(raw, dict):
        inner = raw.get('symbol')
        if isinstance(inner, dict):
            return inner.get('description') or raw.get('description') or symbol
        return raw.get('description') or symbol
    return symbol


def _load_full_export() -> dict:
    """Read the full export JSON; fall back to the newest dated export snapshot."""
    candidates = []
    export_file = os.path.join(ACCOUNT_DATA_DIR, "snaptrade_full_export.json")
    if os.path.exists(export_file):
        candidates.append(export_file)
    dated_exports = sorted(
        glob.glob(os.path.join(ACCOUNT_DATA_DIR, "snaptrade_full_export*.json")),
        key=os.path.getmtime,
        reverse=True,
    )
    for path in dated_exports:
        if path not in candidates:
            candidates.append(path)

    for path in candidates:
        try:
            with open(path, "r") as f:
                data = json.load(f)
            if data:
                return data
        except Exception as exc:
            print(f"[export] Could not read {path}: {exc}")
    return {}


def _get_user_account_wrappers(export=None, account_id=None):
    """Return export account wrappers scoped to the logged-in user/account."""
    user = get_current_user()
    if not user:
        return []

    username = user['username']
    if account_id is None:
        account_id = get_account_id()

    export = export or _load_full_export()
    if not export:
        return []

    if 'users' in export:
        for user_entry in export.get('users', []):
            if user_entry.get('username') == username:
                return user_entry.get('accounts', [])
        return []

    wrappers = []
    for wrapper in export.get('accounts', []):
        acc = wrapper.get('account', {})
        if account_id:
            if acc.get('id') == account_id:
                wrappers.append(wrapper)
        else:
            wrappers.append(wrapper)
    return wrappers


def _positions_from_export_wrappers(wrappers):
    """Reconstruct open positions from export wrappers for one account."""
    symbol_map = {}

    for acc_wrapper in wrappers:
        export_positions = acc_wrapper.get('positions') or []
        if export_positions:
            return export_positions

        activities = acc_wrapper.get('activities', {})
        txns = activities.get('data', []) if isinstance(activities, dict) else []

        for txn in txns:
            symbol = _symbol_from_activity(txn)
            if not symbol:
                continue

            units = float(txn.get('units') or 0)
            price = float(txn.get('price') or 0)
            description = _description_from_activity(txn, symbol)

            if symbol not in symbol_map:
                symbol_map[symbol] = {
                    'symbol': symbol,
                    'description': description,
                    'units': 0.0,
                    'total_cost': 0.0,
                    'last_price': price,
                }

            symbol_map[symbol]['units'] += units
            if units > 0:
                symbol_map[symbol]['total_cost'] += units * price
            if price > 0:
                symbol_map[symbol]['last_price'] = price

    positions = []
    for sym, data in symbol_map.items():
        net_units = round(data['units'], 6)
        if net_units > 0.0001:
            avg_cost = data['total_cost'] / net_units if net_units else 0
            positions.append({
                'symbol': sym,
                'units': net_units,
                'price': data['last_price'],
                'average_purchase_price': avg_cost,
                'description': data['description'],
            })
    return positions

WATCHLIST = [
    'AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','BRK.B','JPM','V',
    'XOM','UNH','JNJ','PG',
    'SPY','QQQ','VOO','VTI','IWM','DIA'
]
SAFE_ASSETS = {
    'SPY','VOO','VTI','QQQ','IWM','DIA','SCHB','ITOT','VT',
    'SCHX','SCHA','SCHM','VB','VO','VV','MGC','MGK','MGV',
    'BND','AGG','TLT','IEF','SHY','VCIT','LQD','BNDX',
    'VCSH','VGSH','VGIT','VGLT','BSV','BIV','BLV',
    'MUB','HYG','JNK','EMB','TIP','SCHZ',
    'SPAXX','FDRXX','VMFXX','SGOV','BIL','SHV','CLTL',
    'GBIL','TFLO','ICSH','NEAR',
}
QUOTE_CACHE = {}
QUOTE_TTL_SECONDS = 60
USE_YAHOO = (os.getenv('USE_YAHOO', '0') == '1')

# Reduce noisy yfinance logging
try:
    logging.getLogger('yfinance').setLevel(logging.ERROR)
except Exception:
    pass
NOTIFICATIONS = []


def _flat_portfolio_history(total_value, chart_start, end_day=None):
    """Flat line fallback from chart_start through end_day."""
    end_day = end_day or datetime.now().date()
    if isinstance(chart_start, datetime):
        chart_start = chart_start.date()
    base = float(total_value or 0)
    history = []
    day = chart_start
    while day <= end_day:
        history.append({'date': day.isoformat(), 'value': round(base, 2)})
        day += timedelta(days=1)
    return history


def _resolve_history_window(days_param, first_date=None):
    """Return (days_for_api, show_all, chart_start_date)."""
    end_day = datetime.now().date()
    if isinstance(first_date, datetime):
        first_date = first_date.date()

    if str(days_param).strip().lower() == 'all':
        chart_start = first_date or (end_day - timedelta(days=365 * 5))
        days = max((end_day - chart_start).days + 1, 1)
        return days, True, chart_start

    days = max(int(days_param), 1)
    window_start = end_day - timedelta(days=max(days - 1, 0))
    chart_start = max(window_start, first_date) if first_date else window_start
    return days, False, chart_start


def _clip_history_to_window(history, chart_start):
    if not history:
        return []
    start_str = chart_start.isoformat() if hasattr(chart_start, 'isoformat') else str(chart_start)[:10]
    return [point for point in history if point.get('date', '') >= start_str]


def _get_account_first_transaction_date(account_id):
    if not account_id:
        return None
    try:
        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return None
        snaptrade_client = get_snaptrade_client()
        response = snaptrade_client.account_information.get_user_account_details(
            user_id=user_id,
            user_secret=user_secret,
            account_id=account_id,
        )
        details = response.body if response.body else {}
        first = (details.get('sync_status') or {}).get('transactions', {}).get('first_transaction_date')
        if first:
            return datetime.strptime(str(first)[:10], '%Y-%m-%d').date()
    except Exception as e:
        print(f"Error getting first transaction date: {e}")
    return None


def _fetch_account_activities_range(snaptrade_client, user_id, user_secret, account_id, start_date, end_date):
    """Paginated account activities for a date range (see test_snaptrade copy.py)."""
    if not account_id:
        return []

    if isinstance(start_date, datetime):
        start_date = start_date.date()
    if isinstance(end_date, datetime):
        end_date = end_date.date()

    activities = []
    for year in range(start_date.year, end_date.year + 1):
        year_start = max(start_date, datetime(year, 1, 1).date())
        year_end = min(end_date, datetime(year, 12, 31).date())
        start_str = year_start.strftime('%Y-%m-%d')
        end_str = year_end.strftime('%Y-%m-%d')
        offset = 0
        limit = 1000

        while True:
            resp = snaptrade_client.account_information.get_account_activities(
                account_id=account_id,
                user_id=user_id,
                user_secret=user_secret,
                start_date=start_str,
                end_date=end_str,
                offset=offset,
                limit=limit,
            )
            batch = _snaptrade_activities_page_items(getattr(resp, 'body', None))
            if not batch:
                break
            activities.extend(batch)
            if len(batch) < limit:
                break
            offset += limit

    return activities


def _activity_dt(activity):
    return _parse_iso_dt(activity.get('trade_date') or activity.get('settlement_date'))


def _build_portfolio_history_from_activities(activities, chart_start, selected_symbols=None):
    """
    Rebuild portfolio value over time from SnapTrade account activities.
    Only includes dates on/after the first activity (no pre-trade history).
    """
    if not activities:
        return []

    sorted_acts = sorted(activities, key=lambda a: _activity_dt(a) or datetime.min)
    first_dt = _activity_dt(sorted_acts[0])
    if not first_dt:
        return []

    end_day = datetime.now().date()
    first_day = first_dt.date()
    if isinstance(chart_start, datetime):
        chart_start = chart_start.date()
    chart_start = max(chart_start, first_day)

    holdings = {}
    cash = 0.0
    timeline = []

    for activity in sorted_acts:
        act_dt = _activity_dt(activity)
        if not act_dt:
            continue

        cash += _to_float(activity.get('amount', 0), 0.0)
        if not activity.get('option_symbol'):
            sym = _symbol_from_activity(activity)
            units = _to_float(activity.get('units', activity.get('quantity', 0)), 0.0)
            act_type = (activity.get('type') or '').upper()
            if sym and sym != 'N/A' and units != 0 and act_type in ('BUY', 'SELL', 'JNLS'):
                holdings[sym] = holdings.get(sym, 0.0) + units
                if abs(holdings.get(sym, 0.0)) < 1e-9:
                    holdings.pop(sym, None)

        timeline.append((act_dt.date(), dict(holdings), cash))

    if not timeline:
        return []

    symbols = set()
    for _, day_holdings, _ in timeline:
        symbols.update(day_holdings.keys())
    if selected_symbols:
        symbols = {sym for sym in symbols if sym in selected_symbols}

    price_series = {}
    start_fetch = datetime.combine(chart_start, datetime.min.time())
    end_fetch = datetime.combine(end_day, datetime.min.time())
    for sym in symbols:
        price_series[sym] = _fetch_symbol_daily_closes(sym, start_fetch, end_fetch)

    last_holdings = {}
    last_cash = 0.0
    timeline_idx = 0
    history = []
    day = chart_start

    while day <= end_day:
        while timeline_idx < len(timeline) and timeline[timeline_idx][0] <= day:
            _, last_holdings, last_cash = timeline[timeline_idx]
            timeline_idx += 1

        active_holdings = last_holdings
        if selected_symbols:
            active_holdings = {sym: qty for sym, qty in last_holdings.items() if sym in selected_symbols}

        day_str = day.isoformat()
        stock_value = 0.0
        for sym, qty in active_holdings.items():
            if qty <= 0:
                continue
            closes = price_series.get(sym, {})
            price = closes.get(day_str)
            if price is None:
                for prior_day in sorted(closes.keys(), reverse=True):
                    if prior_day <= day_str:
                        price = closes[prior_day]
                        break
            if price is not None:
                stock_value += price * qty

        total = stock_value if selected_symbols else (last_cash + stock_value)
        if day >= first_day:
            history.append({'date': day_str, 'value': round(total, 2)})
        day += timedelta(days=1)

    return history


def _fetch_snaptrade_equity_history(account_id=None, chart_start=None, days=30):
    """Load account equity history from SnapTrade reporting (actual portfolio value)."""
    try:
        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return []

        end_date = datetime.now()
        if chart_start:
            if isinstance(chart_start, datetime):
                start_date = chart_start
            else:
                start_date = datetime.combine(chart_start, datetime.min.time())
        else:
            start_date = end_date - timedelta(days=days)
        snaptrade_client = get_snaptrade_client()
        response = snaptrade_client.transactions_and_reporting.get_reporting_custom_range(
            user_id=user_id,
            user_secret=user_secret,
            start_date=start_date.strftime('%Y-%m-%d'),
            end_date=end_date.strftime('%Y-%m-%d'),
            accounts=account_id,
            detailed=True,
            frequency='daily',
        )
        body = response.body if response.body else {}
        if not isinstance(body, dict):
            return []

        points = body.get('totalEquityTimeframe') or []
        history = []
        for point in points:
            if not isinstance(point, dict):
                continue
            date_value = point.get('date')
            amount = point.get('value')
            if date_value is None or amount is None:
                continue
            if hasattr(date_value, 'strftime'):
                date_str = date_value.strftime('%Y-%m-%d')
            else:
                date_str = str(date_value)[:10]
            history.append({'date': date_str, 'value': round(float(amount), 2)})

        history.sort(key=lambda item: item['date'])
        return history
    except Exception as e:
        print(f"Error fetching SnapTrade equity history: {e}")
        return []


def _fetch_symbol_daily_closes(symbol, start_date, end_date):
    """Return {YYYY-MM-DD: close_price} for one symbol."""
    yn = _normalize_symbol_for_yf(symbol)
    try:
        hist = yf.Ticker(yn).history(
            start=start_date,
            end=end_date + timedelta(days=1),
            auto_adjust=True,
            interval='1d'
        )
        if hist is None or len(hist) == 0:
            return {}

        close_col = 'Close' if 'Close' in hist.columns else 'Adj Close'
        closes = {}
        for date, row in hist.iterrows():
            price = row.get(close_col)
            if price is None:
                continue
            try:
                price = float(price)
            except (TypeError, ValueError):
                continue
            if price != price:
                continue
            closes[date.strftime('%Y-%m-%d')] = price
        return closes
    except Exception as e:
        print(f"Error fetching daily data for {symbol}: {e}")
        return {}


def get_account_id():
    """Get the primary SnapTrade account ID for the logged-in user."""
    try:
        user = get_current_user()
        if user:
            account_data = load_account_data()
            user_accounts = account_data.get(user['username'], {}).get('accounts', [])
            if user_accounts:
                return user_accounts[0].get('id')

        user_id, user_secret = get_user_credentials()
        if user_id and user_secret:
            snaptrade_client = get_snaptrade_client()
            accounts_response = snaptrade_client.account_information.list_user_accounts(
                user_id=user_id,
                user_secret=user_secret,
            )
            accounts = accounts_response.body if accounts_response.body else []
            if accounts:
                return accounts[0].get('id')
    except Exception as e:
        print(f"Error getting account ID: {e}")
    return None


def get_portfolio_positions():
    """Get positions from live SnapTrade API, with user-scoped export fallback."""
    try:
        account_id = get_account_id()
        user_id, user_secret = get_user_credentials()
        if account_id and user_id and user_secret:
            snaptrade_client = get_snaptrade_client()
            positions_response = snaptrade_client.account_information.get_user_account_positions(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id,
            )
            body = positions_response.body if positions_response.body else []
            if body:
                return body

        wrappers = _get_user_account_wrappers(account_id=account_id)
        if wrappers:
            return _positions_from_export_wrappers(wrappers)
    except Exception as e:
        print(f"Error getting positions: {e}")
    return []


@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get accounts for the logged-in user."""
    try:
        if not get_current_user():
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        user = get_current_user()
        account_data = load_account_data()
        user_accounts = account_data.get(user['username'], {}).get('accounts', [])
        if user_accounts:
            return jsonify({'success': True, 'data': user_accounts})

        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        snaptrade_client = get_snaptrade_client()
        accounts_response = snaptrade_client.account_information.list_user_accounts(
            user_id=user_id,
            user_secret=user_secret,
        )
        return jsonify({
            'success': True,
            'data': accounts_response.body if accounts_response.body else []
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/portfolio/positions', methods=['GET'])
def get_positions():
    """Get portfolio positions"""
    try:
        if not get_current_user():
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        positions = get_portfolio_positions()
        return jsonify({
            'success': True,
            'data': positions
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/portfolio/summary', methods=['GET'])
def get_portfolio_summary():
    """Get portfolio summary with total value and performance"""
    try:
        if not get_current_user():
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        positions = get_portfolio_positions()

        total_value = 0
        total_cost = 0
        holdings = []
        position_rows = []

        for position in positions:
            norm_symbol = _get_symbol_from_position(position)
            if not norm_symbol or norm_symbol == 'N/A':
                continue

            current_price = position.get('price', 0)
            quantity = position.get('units', 0)
            avg_cost = position.get('average_purchase_price', 0)

            market_value = current_price * quantity
            cost_basis = avg_cost * quantity

            total_value += market_value
            total_cost += cost_basis

            position_rows.append({
                'position': position,
                'symbol': norm_symbol,
                'name': _get_name_from_position(position, norm_symbol),
                'price': current_price,
                'quantity': quantity,
                'marketValue': market_value,
                'costBasis': cost_basis,
            })

        symbols = [row['symbol'] for row in position_rows]
        previous_closes = _fetch_previous_closes(symbols)
        allocation_metadata = _fetch_allocation_metadata(symbols)

        for row in position_rows:
            position = row.pop('position')
            current_price = row['price']
            quantity = row['quantity']
            avg_cost = row['costBasis'] / quantity if quantity else 0
            prev_close = previous_closes.get(row['symbol'])
            daily_change_percent = 0.0
            daily_gain_loss = 0.0
            if prev_close and prev_close > 0:
                daily_change_percent = ((current_price - prev_close) / prev_close) * 100
                daily_gain_loss = (current_price - prev_close) * quantity

            meta = allocation_metadata.get(row['symbol'], {})
            holdings.append({
                **row,
                'change': ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0,
                'dailyChange': daily_change_percent,
                'dailyGainLoss': daily_gain_loss,
                'assetType': _asset_type_from_position(
                    position, row['symbol'], meta.get('assetType')
                ),
                'sector': meta.get('sector') or 'Unknown',
                'isSafeAsset': row['symbol'] in SAFE_ASSETS,
            })

        account_total = _get_account_total_balance()
        if account_total is not None:
            cash_balance = max(0.0, account_total - total_value)
        else:
            cash_balance = _get_cash_balance_from_export()

        total_gain_loss = total_value - total_cost
        total_return = (total_gain_loss / total_cost * 100) if total_cost > 0 else 0

        return jsonify({
            'success': True,
            'data': {
                'totalValue': total_value,
                'totalCost': total_cost,
                'totalGainLoss': total_gain_loss,
                'totalReturn': total_return,
                'cashBalance': cash_balance,
                'holdings': holdings
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new user account and create Snaptrade user"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password are required'}), 400
        
        users = load_users()
        if username in users:
            return jsonify({'success': False, 'error': 'Username already exists'}), 400
        
        # Step 1: Register user with Snaptrade
        snaptrade_client = get_snaptrade_client()
        try:
            register_response = snaptrade_client.authentication.register_snap_trade_user(
                body={'userId': username}
            )
            
            if not register_response.body:
                return jsonify({'success': False, 'error': 'Failed to register with Snaptrade'}), 500
            
            user_id = register_response.body.get('userId')
            user_secret = register_response.body.get('userSecret')
            
            if not user_id or not user_secret:
                return jsonify({'success': False, 'error': 'Invalid Snaptrade response'}), 500
            
        except Exception as e:
            return jsonify({'success': False, 'error': f'Snaptrade registration failed: {str(e)}'}), 500
        
        # Step 2: Generate login URL for brokerage connection
        try:
            login_response = snaptrade_client.authentication.login_snap_trade_user(
                user_id=user_id,
                user_secret=user_secret
            )
            
            if not login_response.body:
                return jsonify({'success': False, 'error': 'Failed to generate connection URL'}), 500
            
            redirect_uri = login_response.body.get('redirectURI')
            session_id = login_response.body.get('sessionId')
            
            if not redirect_uri:
                return jsonify({'success': False, 'error': 'Invalid connection URL response'}), 500
            
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to generate connection URL: {str(e)}'}), 500
        
        # Step 3: Save user data (without logging them in yet)
        users[username] = {
            'username': username,
            'password_hash': hash_password(password),
            'snaptrade_user_id': user_id,
            'snaptrade_user_secret': user_secret,
            'redirect_uri': redirect_uri,
            'session_id': session_id,
            'account_connected': False,
            'created_at': datetime.now().isoformat()
        }
        save_users(users)
        
        return jsonify({
            'success': True,
            'message': 'Account created successfully',
            'redirectURI': redirect_uri,
            'sessionId': session_id
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/complete-setup', methods=['POST'])
def complete_setup():
    """Complete account setup by fetching and storing account data"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
 
        if not username:
            return jsonify({'success': False, 'error': 'Username is required'}), 400
 
        users = load_users()
        user = users.get(username)
 
        if not user:
            return jsonify({'success': False, 'error': 'User not found'}), 404
 
        user_id     = user.get('snaptrade_user_id')
        user_secret = user.get('snaptrade_user_secret')
 
        if not user_id or not user_secret:
            return jsonify({'success': False, 'error': 'Invalid user credentials'}), 400
 
        # ── existing: fetch account list from SnapTrade ───────────────────────
        snaptrade_client = get_snaptrade_client()
        try:
            accounts_response = snaptrade_client.account_information.list_user_accounts(
                user_id=user_id,
                user_secret=user_secret
            )
            if not accounts_response.body:
                return jsonify({'success': False,
                                'error': 'No accounts found. Please connect your brokerage account first.'}), 400
            accounts = accounts_response.body
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to fetch accounts: {str(e)}'}), 500
 
        # ── existing: store light account data to JSON file ───────────────────
        if len(accounts) > 0:
            account_id = accounts[0].get('id')
            try:
                account_details_response = snaptrade_client.account_information.get_user_account_details(
                    account_id=account_id,
                    user_id=user_id,
                    user_secret=user_secret
                )
                account_details = account_details_response.body if account_details_response.body else accounts[0]
            except Exception as e:
                print(f"Error fetching account details: {e}")
                account_details = accounts[0]
        else:
            account_details = None
 
        account_data = load_account_data()
        account_data[username] = {
            'username': username,
            'accounts': accounts,
            'primary_account': account_details,
            'fetched_at': datetime.now().isoformat()
        }
        save_account_data(account_data)
 
        users[username]['account_connected'] = True
        users[username]['accounts_fetched_at'] = datetime.now().isoformat()
        save_users(users)
 
        # ── NEW: populate SQLite DB via ORM ───────────────────────────────────
        # Runs in the same process; errors are non-fatal so setup still succeeds.
        try:
            print("[complete_setup] Syncing export to DB...")
            stats = sync_export_to_db(verbose=True)
            print(f"[complete_setup] DB sync complete: {stats}")
        except Exception as db_err:
            print(f"[complete_setup] ⚠️ DB sync failed (non-fatal): {db_err}")
        # ─────────────────────────────────────────────────────────────────────
 
        return jsonify({
            'success': True,
            'message': 'Account setup completed successfully',
            'accounts': accounts
        })
 
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login user"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        
        if not username or not password:
            return jsonify({'success': False, 'error': 'Username and password are required'}), 400
        
        users = load_users()
        user = users.get(username)
        
        if not user or user['password_hash'] != hash_password(password):
            return jsonify({'success': False, 'error': 'Invalid username or password'}), 401
        
        # Check if account is connected
        if not user.get('account_connected', False):
            return jsonify({
                'success': False,
                'error': 'Account setup not completed. Please complete brokerage connection.',
                'needs_setup': True
            }), 403
        
        session['username'] = username
        return jsonify({
            'success': True,
            'message': 'Login successful',
            'username': username
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    """Logout user"""
    session.pop('username', None)
    return jsonify({'success': True, 'message': 'Logged out successfully'})

@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """Check if user is logged in"""
    user = get_current_user()
    if user:
        return jsonify({
            'success': True,
            'logged_in': True,
            'username': user['username']
        })
    return jsonify({
        'success': True,
        'logged_in': False
    })


def _mask_account_number(number):
    if not number:
        return None
    text = str(number)
    if len(text) <= 4:
        return text
    return f"••••{text[-4:]}"


def _build_user_profile(user):
    username = user.get('username')
    profile = {
        'username': username,
        'createdAt': user.get('created_at'),
        'accountConnected': bool(user.get('account_connected', False)),
        'accountsFetchedAt': user.get('accounts_fetched_at'),
        'brokerage': None,
    }

    account_data = load_account_data()
    stored = account_data.get(username, {})
    primary = stored.get('primary_account') or {}
    accounts = stored.get('accounts') or []

    if not primary and accounts:
        primary = accounts[0]

    if not primary:
        user_id, user_secret = get_user_credentials()
        account_id = get_account_id()
        if user_id and user_secret and account_id:
            try:
                snaptrade_client = get_snaptrade_client()
                response = snaptrade_client.account_information.get_user_account_details(
                    user_id=user_id,
                    user_secret=user_secret,
                    account_id=account_id,
                )
                primary = response.body if response.body else {}
            except Exception as e:
                print(f"Error fetching profile account details: {e}")

    if primary:
        balance = primary.get('balance') or {}
        total = balance.get('total') or {}
        sync_status = primary.get('sync_status') or {}
        holdings_sync = sync_status.get('holdings') or {}
        transactions_sync = sync_status.get('transactions') or {}
        meta = primary.get('meta') or {}
        export_balance = _to_float(primary.get('_export_cash'), None)
        total_balance = _to_float(total.get('amount'), None)
        if total_balance is None:
            total_balance = export_balance

        profile['brokerage'] = {
            'institutionName': primary.get('institution_name') or meta.get('institution_name'),
            'accountName': primary.get('name'),
            'accountNumber': _mask_account_number(primary.get('number')),
            'accountType': meta.get('type'),
            'status': primary.get('status') or meta.get('status'),
            'isPaper': bool(primary.get('is_paper', False)),
            'balance': total_balance,
            'currency': total.get('currency') or 'USD',
            'lastHoldingsSync': holdings_sync.get('last_successful_sync'),
            'lastTransactionsSync': transactions_sync.get('last_successful_sync'),
            'firstTransactionDate': transactions_sync.get('first_transaction_date'),
        }

    return profile


@app.route('/api/auth/profile', methods=['GET'])
def auth_profile():
    """Return safe account profile details for the logged-in user."""
    user = get_current_user()
    if not user:
        return jsonify({'success': False, 'error': 'Not authenticated'}), 401
    return jsonify({
        'success': True,
        'data': _build_user_profile(user),
    })


def _format_transaction_type(activity):
    """Format transaction type for better display"""
    activity_type = activity.get('type', '').upper()
    
    # Handle specific type codes from Snaptrade/Alpaca
    if activity_type == 'JNLC':
        return 'DEPOSIT'
    if activity_type == 'JNLS':
        return 'WITHDRAWAL'
    if activity_type in ('FEE', 'FEES'):
        return 'FEE'
    if activity_type in ('DIV', 'DIVIDEND'):
        return 'DIVIDEND'
    if activity_type in ('INT', 'INTEREST'):
        return 'INTEREST'
    if activity_type in ('BUY', 'SELL'):
        return activity_type
    
    # Default to original type
    return activity_type if activity_type else 'OTHER'

def _format_transaction_description(activity, formatted_type):
    """Format transaction description for better readability"""
    description = activity.get('description', '').strip()
    amount = activity.get('amount', 0)
    symbol = activity.get('symbol', '')
    
    # Normalize symbol - remove "N/A"
    if symbol == 'N/A':
        symbol = ''
    
    # Format based on type
    if formatted_type == 'DEPOSIT':
        if description:
            return description
        return f'Deposit of ${abs(amount):,.2f}'
    
    if formatted_type == 'WITHDRAWAL':
        if description:
            return description
        return f'Withdrawal of ${abs(amount):,.2f}'
    
    if formatted_type == 'FEE':
        if description:
            return description
        return f'Trading fee: ${abs(amount):,.2f}'
    
    if formatted_type in ('DIVIDEND', 'INTEREST'):
        if description:
            return description
        if symbol:
            return f'{formatted_type.title()} from {symbol}'
        return f'{formatted_type.title()} payment'
    
    # For trades (BUY/SELL), the description from the API is already well-formatted
    if description:
        return description
    
    # Fallback if no description
    if symbol:
        return f'{symbol} {formatted_type}'
    
    return f'{formatted_type} transaction'

def _parse_transaction_description(description, symbol):
    """Parse transaction description to separate action type from details"""
    if not description:
        return 'Transaction', description
    
    # Common patterns in descriptions
    desc_upper = description.upper()
    
    # Check for BUY variations
    if 'BUY PARTIAL_FILL' in desc_upper:
        action = 'BUY PARTIAL_FILL'
    elif 'BUY FILL' in desc_upper:
        action = 'BUY FILL'
    elif 'BUY' in desc_upper:
        action = 'BUY'
    # Check for SELL variations
    elif 'SELL PARTIAL_FILL' in desc_upper:
        action = 'SELL PARTIAL_FILL'
    elif 'SELL FILL' in desc_upper:
        action = 'SELL FILL'
    elif 'SELL' in desc_upper:
        action = 'SELL'
    # Check for other types
    elif 'DEPOSIT' in desc_upper or 'JNLC' in desc_upper:
        action = 'DEPOSIT'
    elif 'WITHDRAWAL' in desc_upper or 'JNLS' in desc_upper:
        action = 'WITHDRAWAL'
    elif 'FEE' in desc_upper:
        action = 'FEE'
    elif 'DIVIDEND' in desc_upper or 'DIV' in desc_upper:
        action = 'DIVIDEND'
    elif 'INTEREST' in desc_upper or 'INT' in desc_upper:
        action = 'INTEREST'
    else:
        action = 'Transaction'
    
    # Extract price if present (e.g., "at 612.17")
    price_match = None
    price_pattern = r'at\s+([\d,.]+)'
    match = re.search(price_pattern, description, re.IGNORECASE)
    if match:
        price_match = match.group(1)
    
    return action, price_match


def _to_float(value, default=0.0):
    try:
        if value is None or value == '':
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def _normalize_option_metadata(activity):
    option_symbol = activity.get('option_symbol')
    if not isinstance(option_symbol, dict):
        return {
            'isOption': False,
            'underlyingSymbol': None,
            'strikePrice': None,
            'optionType': None,
            'expirationDate': None,
            'contractCount': 0.0,
            'positionSide': None
        }

    units = _to_float(activity.get('units', activity.get('quantity', 0)), 0.0)
    underlying = option_symbol.get('underlying_symbol')
    underlying_symbol = None
    if isinstance(underlying, dict):
        underlying_symbol = underlying.get('symbol') or underlying.get('raw_symbol')

    option_type = (option_symbol.get('option_type') or '').upper()
    if option_type not in ('CALL', 'PUT'):
        option_type = None

    position_side = None
    if units > 0:
        position_side = 'LONG'
    elif units < 0:
        position_side = 'SHORT'

    return {
        'isOption': True,
        'underlyingSymbol': underlying_symbol,
        'strikePrice': _to_float(option_symbol.get('strike_price'), None),
        'optionType': option_type,
        'expirationDate': option_symbol.get('expiration_date'),
        'contractCount': abs(units),
        'positionSide': position_side
    }

def _normalize_type_label(raw_type, action, is_option):
    type_upper = (raw_type or '').upper()
    action_upper = (action or '').upper()

    if type_upper == 'JNLC':
        return 'DEPOSIT'
    if type_upper == 'JNLS':
        return 'WITHDRAWAL'
    if type_upper in ('FEE', 'FEES'):
        return 'FEE'
    if type_upper in ('DIV', 'DIVIDEND'):
        return 'DIVIDEND'
    if type_upper in ('INT', 'INTEREST'):
        return 'INTEREST'

    if is_option:
        if 'EXERCISE' in type_upper or 'EXERCISE' in action_upper:
            return 'EXERCISE'
        if 'ASSIGN' in type_upper or 'ASSIGN' in action_upper:
            return 'ASSIGNMENT'
        if 'OPEN' in action_upper:
            return 'OPEN'
        if 'CLOSE' in action_upper:
            return 'CLOSE'

    return type_upper if type_upper else 'OTHER'

def _parse_iso_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
    except Exception:
        return None

def _option_key(option_type, strike_price, expiration_date, underlying_symbol):
    return f"{underlying_symbol or ''}|{option_type or ''}|{strike_price or ''}|{expiration_date or ''}"


def _should_include_option_order(order):
    """Only surface option orders that are active or have fills."""
    filled_qty = _to_float(order.get('filled_quantity', 0), 0.0)
    total_qty = _to_float(order.get('total_quantity', filled_qty), filled_qty)
    status = (order.get('status') or '').upper()
    active_statuses = {
        'PENDING', 'OPEN', 'NEW', 'ACCEPTED', 'QUEUED', 'WORKING',
        'PARTIALLY_FILLED', 'PARTIAL',
    }
    if filled_qty > 0:
        return True
    if status in ('EXECUTED', 'FILLED'):
        return filled_qty > 0
    if status in active_statuses and total_qty > 0:
        return True
    return False


def _append_option_order_row(rows, order, matched_fee=0.0):
    option_symbol = order.get('option_symbol')
    if not isinstance(option_symbol, dict):
        return False
    if not _should_include_option_order(order):
        return False

    underlying = option_symbol.get('underlying_symbol')
    underlying_symbol = None
    if isinstance(underlying, dict):
        underlying_symbol = underlying.get('symbol') or underlying.get('raw_symbol')

    option_type = (option_symbol.get('option_type') or '').upper()
    if option_type not in ('CALL', 'PUT'):
        option_type = None

    filled_qty = _to_float(order.get('filled_quantity', order.get('total_quantity', 0)), 0.0)
    total_qty = _to_float(order.get('total_quantity', filled_qty), filled_qty)
    action = (order.get('action') or '').upper()
    position_side = 'LONG' if 'BUY' in action else ('SHORT' if 'SELL' in action else None)
    limit_price = _to_float(order.get('limit_price'), 0.0)
    execution_price = _to_float(order.get('execution_price'), 0.0)
    status_value = order.get('status') or 'UNKNOWN'
    placed_time = order.get('time_placed')
    executed_time = order.get('time_executed')
    qty_for_display = filled_qty if filled_qty > 0 else total_qty

    order_amount = execution_price * filled_qty * 100
    if 'BUY' in action:
        order_amount = -abs(order_amount)
    elif 'SELL' in action:
        order_amount = abs(order_amount)

    rows.append({
        'id': f"order_{order.get('brokerage_order_id')}",
        'symbol': underlying_symbol or 'N/A',
        'type': 'OPTION_ORDER',
        'typeLabel': _normalize_type_label('OPTION_ORDER', action, True),
        'action': action or 'ORDER',
        'description': f"Order {status_value}",
        'priceFromDescription': None,
        'date': executed_time or placed_time or '',
        'tradeDate': executed_time,
        'settlementDate': None,
        'amount': order_amount,
        'fee': matched_fee,
        'netAmount': order_amount - matched_fee,
        'quantity': qty_for_display,
        'units': qty_for_display,
        'filledQuantity': filled_qty,
        'price': execution_price,
        'isOption': True,
        'underlyingSymbol': underlying_symbol,
        'strikePrice': _to_float(option_symbol.get('strike_price'), None),
        'optionType': option_type,
        'expirationDate': option_symbol.get('expiration_date'),
        'contractCount': qty_for_display,
        'positionSide': position_side,
        'limitPrice': limit_price,
        'executionPrice': execution_price,
        'placedTime': placed_time,
        'executedTime': executed_time,
        'feeBreakdown': {
            'occClearingFee': 0.0,
            'orfFee': 0.0,
            'otherFees': matched_fee
        },
        'status': status_value,
        'source': 'order'
    })
    return True


def _load_option_orders_from_latest_export():
    """Fallback: load option orders from export scoped to the logged-in user."""
    try:
        rows = []
        for acc_wrapper in _get_user_account_wrappers():
            orders = acc_wrapper.get('orders', []) if isinstance(acc_wrapper, dict) else []
            for order in orders:
                option_symbol = order.get('option_symbol')
                if not isinstance(option_symbol, dict):
                    continue
                matched_fee = 0.0
                _append_option_order_row(rows, order, matched_fee)
        return rows
    except Exception as export_err:
        print(f"Error loading option orders from export: {export_err}")
        return []


def _snaptrade_activities_page_items(page_body):
    """
    Account-level activities return PaginatedUniversalActivity: { "data": [...], "pagination": {...} }.
    User-level get_activities returns a plain list. Normalize to a list of activity dicts.
    """
    if page_body is None:
        return []
    if isinstance(page_body, list):
        return page_body
    if isinstance(page_body, dict):
        return page_body.get('data') or []
    data = getattr(page_body, 'data', None)
    if data is not None:
        return list(data) if not isinstance(data, list) else data
    return []


def _fetch_activities_body(snaptrade_client, user_id, user_secret, account_id):
    """
    Load universal activities for the dashboard transaction table.
    Prefer the account-scoped endpoint so the list matches a single brokerage
    account (same as positions and option orders). The user-level get_activities
    API returns activities across *all* connections for that SnapTrade user,
    which often explodes the count (e.g. hundreds) vs. what you see for one account.
    """
    if account_id:
        activities_body = []
        offset = 0
        page_size = 1000
        while True:
            resp = snaptrade_client.account_information.get_account_activities(
                account_id=account_id,
                user_id=user_id,
                user_secret=user_secret,
                offset=offset,
                limit=page_size,
            )
            page_body = getattr(resp, 'body', None)
            batch = _snaptrade_activities_page_items(page_body)
            if not batch:
                break
            activities_body.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return activities_body
    activities_response = snaptrade_client.transactions_and_reporting.get_activities(
        user_id=user_id,
        user_secret=user_secret
    )
    return getattr(activities_response, 'body', None) or []


@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get recent transactions"""
    try:
        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        snaptrade_client = get_snaptrade_client()
        account_id = get_account_id()
        transactions = []
        activities_body = _fetch_activities_body(
            snaptrade_client, user_id, user_secret, account_id
        )
        option_activity_candidates = []
        if activities_body:
            for activity in activities_body:
                norm_symbol = _symbol_from_activity(activity) or 'N/A'
                
                description = activity.get('description', '')
                action, price_from_desc = _parse_transaction_description(description, norm_symbol)
                option_meta = _normalize_option_metadata(activity)
                amount = _to_float(activity.get('amount', 0), 0.0)
                fee = _to_float(activity.get('fee', 0), 0.0)
                units = _to_float(activity.get('units', activity.get('quantity', 0)), 0.0)
                price = _to_float(activity.get('price', 0), 0.0)
                type_label = _normalize_type_label(activity.get('type', 'Unknown'), action, option_meta['isOption'])
                
                transactions.append({
                    'id': activity.get('id'),
                    'symbol': norm_symbol,
                    'type': activity.get('type', 'Unknown'),
                    'typeLabel': type_label,
                    'action': action,
                    'description': description,
                    'priceFromDescription': price_from_desc,
                    'date': activity.get('trade_date', activity.get('settlement_date', '')),
                    'tradeDate': activity.get('trade_date'),
                    'settlementDate': activity.get('settlement_date'),
                    'amount': amount,
                    'fee': fee,
                    'netAmount': amount - fee,
                    'quantity': units,
                    'units': units,
                    'price': price,
                    'isOption': option_meta['isOption'],
                    'underlyingSymbol': option_meta['underlyingSymbol'],
                    'strikePrice': option_meta['strikePrice'],
                    'optionType': option_meta['optionType'],
                    'expirationDate': option_meta['expirationDate'],
                    'contractCount': option_meta['contractCount'],
                    'positionSide': option_meta['positionSide'],
                    'limitPrice': None,
                    'executionPrice': price,
                    'placedTime': activity.get('trade_date'),
                    'executedTime': activity.get('trade_date'),
                    'feeBreakdown': {
                        'occClearingFee': 0.0,
                        'orfFee': 0.0,
                        'otherFees': fee
                    },
                    'source': 'activity',
                    'status': 'Success'
                })
                if option_meta['isOption']:
                    option_activity_candidates.append({
                        'key': _option_key(
                            option_meta['optionType'],
                            option_meta['strikePrice'],
                            option_meta['expirationDate'],
                            option_meta['underlyingSymbol']
                        ),
                        'side': 'BUY' if amount < 0 else 'SELL',
                        'units': abs(units),
                        'price': price,
                        'fee': fee,
                        'dt': _parse_iso_dt(activity.get('trade_date') or activity.get('settlement_date'))
                    })

        # Option orders from primary account only (same account_id as activities above).
        seen_order_ids = set()
        order_rows_added = 0
        if account_id:
            try:
                orders_response = snaptrade_client.account_information.get_user_account_orders(
                    user_id=user_id,
                    user_secret=user_secret,
                    account_id=account_id
                )
                orders_body = getattr(orders_response, 'body', None) or []
                option_order_rows = []
                for order in orders_body:
                    order_id = order.get('brokerage_order_id')
                    if order_id and order_id in seen_order_ids:
                        continue

                    option_symbol = order.get('option_symbol')
                    if not isinstance(option_symbol, dict):
                        continue
                    if not _should_include_option_order(order):
                        continue

                    filled_qty = _to_float(order.get('filled_quantity', order.get('total_quantity', 0)), 0.0)
                    total_qty = _to_float(order.get('total_quantity', filled_qty), filled_qty)
                    action = (order.get('action') or '').upper()
                    side = 'BUY' if 'BUY' in action else ('SELL' if 'SELL' in action else None)
                    execution_price = _to_float(order.get('execution_price'), 0.0)
                    placed_time = order.get('time_placed')
                    executed_time = order.get('time_executed')
                    order_dt = _parse_iso_dt(executed_time or placed_time)
                    option_type = (option_symbol.get('option_type') or '').upper()
                    if option_type not in ('CALL', 'PUT'):
                        option_type = None
                    underlying = option_symbol.get('underlying_symbol')
                    underlying_symbol = None
                    if isinstance(underlying, dict):
                        underlying_symbol = underlying.get('symbol') or underlying.get('raw_symbol')
                    key = _option_key(
                        option_type,
                        _to_float(option_symbol.get('strike_price'), None),
                        option_symbol.get('expiration_date'),
                        underlying_symbol
                    )
                    qty_for_display = filled_qty if filled_qty > 0 else total_qty
                    matched_fee = 0.0
                    best_delta = None
                    for candidate in option_activity_candidates:
                        if candidate['key'] != key or candidate['side'] != side:
                            continue
                        if qty_for_display > 0 and candidate['units'] > 0 and abs(candidate['units'] - qty_for_display) > 0.0001:
                            continue
                        if execution_price > 0 and candidate['price'] > 0 and abs(candidate['price'] - execution_price) > 0.02:
                            continue
                        if order_dt and candidate['dt']:
                            delta = abs((candidate['dt'] - order_dt).total_seconds())
                        else:
                            delta = 0
                        if best_delta is None or delta < best_delta:
                            best_delta = delta
                            matched_fee = candidate['fee']

                    if _append_option_order_row(option_order_rows, order, matched_fee):
                        if order_id:
                            seen_order_ids.add(order_id)
                        order_rows_added += 1

                transactions.extend(option_order_rows)
            except Exception as order_err:
                print(f"Error getting option orders: {order_err}")

        # Fallback to exported JSON snapshot when API order fetch returns nothing.
        if order_rows_added == 0:
            transactions.extend(_load_option_orders_from_latest_export())
        
        # Sort transactions by date (descending), then by time (descending), then by symbol (ascending)
        transactions.sort(key=lambda x: (
            -datetime.fromisoformat(x['date'].replace('Z', '+00:00')).timestamp() if x['date'] else 0,
            x['symbol']
        ))
        
        return jsonify({
            'success': True,
            'data': transactions
        })
    except Exception as e:
        print(f"Error getting transactions: {e}")
        return jsonify({
            'success': True,
            'data': []
        })


@app.route('/api/portfolio/stocks', methods=['GET'])
def get_portfolio_stocks():
    """Get list of all stocks in portfolio for filtering"""
    try:
        if not get_current_user():
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        positions = get_portfolio_positions()
        stocks = []
        seen_symbols = set()
        
        for position in positions:
            sym = _get_symbol_from_position(position)
            if sym and sym != 'N/A' and sym not in seen_symbols:
                quantity = position.get('units', 0)
                current_price = position.get('price', 0)
                market_value = current_price * quantity
                
                name = sym
                symbol_obj = position.get('symbol')
                if isinstance(symbol_obj, dict):
                    inner_symbol = symbol_obj.get('symbol')
                    if isinstance(inner_symbol, dict):
                        name = inner_symbol.get('description', symbol_obj.get('description', sym))
                    else:
                        name = symbol_obj.get('description', sym)
                
                stocks.append({
                    'symbol': sym,
                    'name': name,
                    'quantity': quantity,
                    'marketValue': market_value
                })
                seen_symbols.add(sym)
        
        return jsonify({'success': True, 'data': stocks})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/portfolio/history', methods=['GET'])
def get_portfolio_history():
    """Return historical portfolio values from SnapTrade (not pre-trade yfinance guesses)."""
    try:
        if not get_current_user():
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401

        days_param = request.args.get('days', 30)
        selected_symbols = request.args.get('symbols', '').split(',') if request.args.get('symbols') else []
        selected_symbols = [s.strip().upper() for s in selected_symbols if s.strip()]

        account_id = get_account_id()
        user_id, user_secret = get_user_credentials()
        first_date = _get_account_first_transaction_date(account_id) if account_id else None
        end_day = datetime.now().date()
        days, show_all, chart_start = _resolve_history_window(days_param, first_date)

        if not selected_symbols:
            reporting_history = _fetch_snaptrade_equity_history(
                account_id=account_id,
                chart_start=chart_start,
                days=days,
            )
            reporting_history = _clip_history_to_window(reporting_history, chart_start)
            if reporting_history:
                return jsonify({
                    'success': True,
                    'data': reporting_history,
                    'source': 'snaptrade_reporting',
                    'timeframe': 'all' if show_all else days,
                })

        if account_id and user_id and user_secret:
            snaptrade_client = get_snaptrade_client()
            fetch_start = first_date or chart_start
            if isinstance(fetch_start, datetime):
                fetch_start = fetch_start.date()
            activities = _fetch_account_activities_range(
                snaptrade_client,
                user_id,
                user_secret,
                account_id,
                fetch_start,
                datetime.combine(end_day, datetime.max.time()),
            )
            activity_history = _build_portfolio_history_from_activities(
                activities,
                chart_start,
                selected_symbols or None,
            )
            if activity_history:
                return jsonify({
                    'success': True,
                    'data': activity_history,
                    'source': 'snaptrade_activities',
                    'timeframe': 'all' if show_all else days,
                })

        summary_response = get_portfolio_summary()
        summary = summary_response.get_json() if hasattr(summary_response, 'get_json') else {}
        total_value = summary.get('data', {}).get('totalValue', 0) if summary else 0
        history = _flat_portfolio_history(total_value, chart_start, end_day)
        return jsonify({
            'success': True,
            'data': history,
            'source': 'flat_fallback',
            'timeframe': 'all' if show_all else days,
        })

    except Exception as e:
        print(f"Error in get_portfolio_history: {e}")
        end_day = datetime.now().date()
        return jsonify({
            'success': True,
            'data': _flat_portfolio_history(0, end_day, end_day),
            'source': 'flat_fallback'
        })


@app.route('/api/benchmark/history', methods=['GET'])
def get_benchmark_history():
    """Get historical data for benchmark"""
    try:
        symbol = _normalize_symbol_for_yf(request.args.get('symbol', 'SPY').upper())
        first_date = _get_account_first_transaction_date(get_account_id())
        days, _, chart_start = _resolve_history_window(request.args.get('days', 180), first_date)

        end_date = datetime.now()
        if isinstance(chart_start, datetime):
            start_date = chart_start
        else:
            start_date = datetime.combine(chart_start, datetime.min.time())

        try:
            hist = yf.Ticker(symbol).history(
                start=start_date,
                end=end_date + timedelta(days=1),
                auto_adjust=True,
                interval='1d'
            )

            if hist is not None and len(hist) > 0:
                close_col = 'Close' if 'Close' in hist.columns else 'Adj Close'
                history = []
                for date, row in hist.iterrows():
                    price = row.get(close_col)
                    if price is None:
                        continue
                    try:
                        price = float(price)
                    except (TypeError, ValueError):
                        continue
                    if price != price:
                        continue
                    history.append({
                        'date': date.strftime('%Y-%m-%d'),
                        'value': price
                    })

                if history:
                    return jsonify({'success': True, 'data': history, 'symbol': symbol})
        except Exception as e:
            print(f"Error fetching benchmark data for {symbol}: {e}")

        return jsonify({'success': False, 'error': f'Could not fetch data for {symbol}'}), 500

    except Exception as e:
        print(f"Error in get_benchmark_history: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _get_symbol_from_position(position):
    """Extract symbol from position object"""
    sym = position.get('symbol')
    if isinstance(sym, dict):
        inner_symbol = sym.get('symbol')
        if isinstance(inner_symbol, dict):
            return inner_symbol.get('symbol') or inner_symbol.get('raw_symbol') or 'N/A'
        return inner_symbol or sym.get('raw_symbol') or 'N/A'
    return str(sym) if sym else 'N/A'


def _get_name_from_position(position, sym):
    """Extract display name from a position object."""
    if position.get('description'):
        return position['description']
    symbol_obj = position.get('symbol')
    if isinstance(symbol_obj, dict):
        inner_symbol = symbol_obj.get('symbol')
        if isinstance(inner_symbol, dict):
            return inner_symbol.get('description', symbol_obj.get('description', sym))
        return symbol_obj.get('description', sym)
    return sym


def _get_inner_symbol_type(position):
    symbol_obj = position.get('symbol')
    if not isinstance(symbol_obj, dict):
        return {}
    inner_symbol = symbol_obj.get('symbol')
    if isinstance(inner_symbol, dict):
        type_obj = inner_symbol.get('type')
        return type_obj if isinstance(type_obj, dict) else {}
    type_obj = symbol_obj.get('type')
    return type_obj if isinstance(type_obj, dict) else {}


def _asset_type_from_position(position, symbol, yf_asset_type=None):
    if position.get('cash_equivalent'):
        return 'Cash Equivalent'
    if isinstance(symbol, str) and symbol in SAFE_ASSETS:
        return 'ETF'
    type_obj = _get_inner_symbol_type(position)
    code = (type_obj.get('code') or '').lower()
    desc = (type_obj.get('description') or '').strip()
    code_map = {
        'cs': 'Stock',
        'ps': 'Stock',
        'ad': 'Stock',
        'et': 'ETF',
        'etf': 'ETF',
        'oef': 'Fund',
        'cef': 'Fund',
        'bnd': 'Bond',
        'ut': 'Unit',
        'crypto': 'Crypto',
        'cry': 'Crypto',
    }
    if code in code_map:
        return code_map[code]
    if desc:
        lower = desc.lower()
        if 'etf' in lower:
            return 'ETF'
        if 'common stock' in lower or lower == 'equity':
            return 'Stock'
        return desc
    if yf_asset_type:
        return yf_asset_type
    return 'Stock'


ALLOCATION_META_CACHE = {}
ALLOCATION_META_TTL_SECONDS = 300


def _fetch_allocation_metadata(symbols):
    """Return {symbol: {sector, assetType}} using yfinance with short-lived cache."""
    results = {}
    for symbol in symbols:
        if not isinstance(symbol, str):
            continue
        symbol = symbol.strip()
        if not symbol:
            continue
        cached = ALLOCATION_META_CACHE.get(symbol)
        if cached and (datetime.now() - cached['ts']).total_seconds() < ALLOCATION_META_TTL_SECONDS:
            results[symbol] = cached['data']
            continue

        meta = {'sector': 'Unknown', 'assetType': None}
        try:
            yn = _normalize_symbol_for_yf(symbol)
            info = yf.Ticker(yn).info or {}
            meta['sector'] = info.get('sector') or info.get('industry') or 'Unknown'
            quote_type = (info.get('quoteType') or '').upper()
            if quote_type == 'ETF':
                meta['assetType'] = 'ETF'
            elif quote_type == 'EQUITY':
                meta['assetType'] = 'Stock'
            elif quote_type in ('MUTUALFUND', 'MUTUAL_FUND'):
                meta['assetType'] = 'Fund'
        except Exception as e:
            print(f"Error fetching allocation metadata for {symbol}: {e}")

        ALLOCATION_META_CACHE[symbol] = {'ts': datetime.now(), 'data': meta}
        results[symbol] = meta
    return results


def _fetch_previous_closes(symbols):
    """Return {symbol: previous_trading_day_close} for daily change calculations."""
    results = {}
    for symbol in symbols:
        if not isinstance(symbol, str):
            continue
        symbol = symbol.strip()
        if not symbol or symbol in results:
            continue
        yn = _normalize_symbol_for_yf(symbol)
        try:
            hist = yf.Ticker(yn).history(period='5d', interval='1d', auto_adjust=True)
            if hist is None or len(hist) == 0:
                continue
            close_col = 'Close' if 'Close' in hist.columns else 'Adj Close'
            closes = hist[close_col].dropna()
            if len(closes) >= 2:
                results[symbol] = float(closes.iloc[-2])
            elif len(closes) == 1:
                results[symbol] = float(closes.iloc[0])
        except Exception as e:
            print(f"Error fetching previous close for {symbol}: {e}")
    return results


def _get_account_total_balance():
    try:
        account_id = get_account_id()
        user_id, user_secret = get_user_credentials()
        if not account_id or not user_id or not user_secret:
            return None

        snaptrade_client = get_snaptrade_client()
        response = snaptrade_client.account_information.get_user_account_details(
            user_id=user_id,
            user_secret=user_secret,
            account_id=account_id,
        )
        details = response.body if response.body else {}
        balance = details.get('balance') or {}
        total = balance.get('total') or {}
        return _to_float(total.get('amount'), None)
    except Exception as e:
        print(f"Error getting account balance: {e}")
        return None


def _get_cash_balance_from_export():
    try:
        account_id = get_account_id()
        user_id, user_secret = get_user_credentials()
        if account_id and user_id and user_secret:
            snaptrade_client = get_snaptrade_client()
            response = snaptrade_client.account_information.get_user_account_details(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id,
            )
            details = response.body if response.body else {}
            balance = details.get('balance') or {}
            total = balance.get('total') or {}
            amount = _to_float(total.get('amount'), None)
            if amount is not None:
                return max(0.0, amount)

            balance_response = snaptrade_client.account_information.get_user_account_balance(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id,
            )
            balances = balance_response.body if balance_response.body else []
            if balances:
                cash = _to_float(balances[0].get('cash'), None)
                if cash is not None:
                    return max(0.0, cash)
    except Exception as e:
        print(f"Error getting live cash balance: {e}")

    for acc_wrapper in _get_user_account_wrappers():
        balances = acc_wrapper.get('balances') or [{}]
        bal = balances[0] if balances else {}
        cash = _to_float(bal.get('cash'), None)
        if cash is not None:
            return max(0.0, cash)
        account = acc_wrapper.get('account') or {}
        total = (account.get('balance') or {}).get('total') or {}
        amount = _to_float(total.get('amount'), None)
        if amount is not None:
            return max(0.0, amount)

    return 0.0


@app.route('/api/watchlist', methods=['GET', 'POST', 'DELETE'])
def watchlist_handler():
    """Simple in-memory watchlist"""
    try:
        if request.method == 'GET':
            return jsonify({'success': True, 'data': WATCHLIST})
        payload = request.get_json(silent=True) or {}
        symbol = (payload.get('symbol') or '').upper().strip()
        if not symbol:
            return jsonify({'success': False, 'error': 'symbol required'}), 400
        if request.method == 'POST':
            if symbol not in WATCHLIST:
                WATCHLIST.append(symbol)
            return jsonify({'success': True, 'data': WATCHLIST})
        if request.method == 'DELETE':
            if symbol in WATCHLIST:
                WATCHLIST.remove(symbol)
            return jsonify({'success': True, 'data': WATCHLIST})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


def _quote_from_cache(symbol: str):
    entry = QUOTE_CACHE.get(symbol)
    if not entry:
        return None
    if (datetime.now() - entry['ts']).total_seconds() > QUOTE_TTL_SECONDS:
        return None
    return entry['data']


def _store_quote_cache(symbol: str, data: dict):
    QUOTE_CACHE[symbol] = {'ts': datetime.now(), 'data': data}


def _mock_quote(symbol: str):
    base = 100 + (abs(hash(symbol)) % 500)
    jitter = (os.urandom(1)[0] / 255.0 - 0.5) * 2
    price = round(base + jitter, 2)
    return {
        'symbol': symbol,
        'name': symbol,
        'price': price,
        'changePercent': round(jitter, 2),
        'updated': datetime.now().isoformat()
    }


def _normalize_symbol_for_yf(symbol: str) -> str:
    return symbol.replace('.', '-')


def _fetch_quote_yf(symbol: str):
    if not USE_YAHOO:
        return _quote_from_cache(symbol) or _mock_quote(symbol)
    cached = _quote_from_cache(symbol)
    if cached:
        return cached
    yn = _normalize_symbol_for_yf(symbol)
    price = None
    prev_close = None
    name = None
    try:
        hist = yf.Ticker(yn).history(period='5d', interval='1d', auto_adjust=False)
        if hist is not None and len(hist.index) > 0 and 'Close' in hist:
            closes = hist['Close'].dropna()
            if len(closes) >= 1:
                price = float(closes.iloc[-1])
            if len(closes) >= 2:
                prev_close = float(closes.iloc[-2])
    except Exception:
        pass
    if price is None:
        try:
            fi = getattr(yf.Ticker(yn), 'fast_info', None) or {}
            price = fi.get('last_price') or fi.get('last_trade_price')
            prev_close = prev_close if prev_close is not None else fi.get('previous_close')
        except Exception:
            pass
    change_pct = 0.0
    if price is None or (isinstance(price, float) and not price):
        data = _mock_quote(symbol)
        _store_quote_cache(symbol, data)
        return data
    if prev_close not in (None, 0):
        change_pct = ((price - prev_close) / prev_close) * 100.0
    data = {
        'symbol': symbol,
        'name': name or symbol,
        'price': round(float(price or 0), 2),
        'changePercent': round(float(change_pct), 2),
        'updated': datetime.now().isoformat()
    }
    _store_quote_cache(symbol, data)
    return data


def _batch_quotes_yf(symbols):
    """Fetch quotes with per-symbol lightweight history method"""
    results = {}
    if not symbols:
        return results
    symbols = list(dict.fromkeys(symbols))[:10]
    for sym in symbols:
        cached = _quote_from_cache(sym)
        if cached:
            results[sym] = cached
            continue
        if not USE_YAHOO:
            results[sym] = _mock_quote(sym)
            continue
        try:
            results[sym] = _fetch_quote_yf(sym)
        except Exception:
            results[sym] = _quote_from_cache(sym) or _mock_quote(sym)
    return results
@app.route('/api/symbols/quote', methods=['GET'])
def get_symbol_quote():
    """Return a cached or live quote for a single symbol"""
    try:
        symbol = (request.args.get('symbol') or '').upper().strip()
        if not symbol:
            return jsonify({'success': False, 'error': 'symbol required'}), 400
        data = _fetch_quote_yf(symbol)
        return jsonify({'success': True, 'data': data})
    except Exception as e:
        cached = _quote_from_cache(symbol) if 'symbol' in locals() else None
        return jsonify({'success': True, 'data': cached or _mock_quote(symbol if 'symbol' in locals() else 'SYM')})
@app.route('/api/watchlist/quotes', methods=['GET'])
def get_watchlist_quotes():
    """Return batched quotes for watchlist"""
    try:
        symbols_param = request.args.get('symbols')
        symbols = []
        if symbols_param:
            symbols = [s.upper().strip() for s in symbols_param.split(',') if s.strip()]
        else:
            symbols = WATCHLIST[:]
        batch_map = _batch_quotes_yf(symbols)
        quotes = []
        for sym in symbols:
            if sym in batch_map:
                quotes.append(batch_map[sym])
                continue
            try:
                quotes.append(_fetch_quote_yf(sym))
            except Exception:
                cached = _quote_from_cache(sym)
                quotes.append(cached or _mock_quote(sym))
        return jsonify({'success': True, 'data': quotes})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/search', methods=['GET'])
def search():
    """Search holdings and watchlist by symbol/name"""
    try:
        q = (request.args.get('q') or '').lower().strip()
        summary_resp = get_portfolio_summary().json
        holdings = (summary_resp.get('data') or {}).get('holdings', []) if summary_resp else []
        results = []
        if q:
            for h in holdings:
                if q in str(h.get('symbol', '')).lower() or q in str(h.get('name', '')).lower():
                    results.append({'type': 'holding', **h})
            for s in WATCHLIST:
                if q in s.lower():
                    results.append({'type': 'watchlist', 'symbol': s})
        return jsonify({'success': True, 'data': results})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/orders/preview', methods=['POST'])
def order_preview():
    """Preview an order cost (mock)"""
    try:
        payload = request.get_json(force=True)
        symbol = (payload.get('symbol') or '').upper().strip()
        side = (payload.get('side') or '').lower().strip()
        quantity = int(payload.get('quantity') or 0)
        if not symbol or side not in ('buy', 'sell') or quantity <= 0:
            return jsonify({'success': False, 'error': 'symbol, side (buy/sell), quantity>0 required'}), 400
        quote_resp = get_symbol_quote()
        quote = quote_resp.json.get('data') if hasattr(quote_resp, 'json') else None
        price = (quote or {}).get('price', 100)
        est_cost = round(price * quantity * (1 if side == 'buy' else -1), 2)
        fees = 0
        return jsonify({'success': True, 'data': {'symbol': symbol, 'side': side, 'quantity': quantity, 'price': price, 'estimatedCost': est_cost, 'fees': fees}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/orders/place', methods=['POST'])
def order_place():
    """Place an order (mock success)"""
    try:
        payload = request.get_json(force=True)
        symbol = (payload.get('symbol') or '').upper().strip()
        side = (payload.get('side') or '').lower().strip()
        quantity = int(payload.get('quantity') or 0)
        if not symbol or side not in ('buy', 'sell') or quantity <= 0:
            return jsonify({'success': False, 'error': 'symbol, side (buy/sell), quantity>0 required'}), 400
        NOTIFICATIONS.append({'type': 'order', 'message': f"{side.upper()} {quantity} {symbol}", 'time': datetime.now().isoformat()})
        return jsonify({'success': True, 'data': {'orderId': f'ord_{int(datetime.now().timestamp())}', 'status': 'accepted'}})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/notifications', methods=['GET', 'POST', 'DELETE'])
def notifications_handler():
    try:
        if request.method == 'GET':
            return jsonify({'success': True, 'data': NOTIFICATIONS})
        if request.method == 'POST':
            payload = request.get_json(silent=True) or {}
            msg = payload.get('message') or 'Test notification'
            NOTIFICATIONS.append({'type': 'info', 'message': msg, 'time': datetime.now().isoformat()})
            return jsonify({'success': True, 'data': NOTIFICATIONS})
        if request.method == 'DELETE':
            NOTIFICATIONS.clear()
            return jsonify({'success': True, 'data': []})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/', methods=['GET'])
def index():
    """Root info route — the backend is API-only; this just confirms it's up."""
    return jsonify({
        'service': 'TradePerformanceVisualizer API',
        'status': 'running',
        'note': 'This is an API-only backend. Use the frontends, not this URL directly.',
        'endpoints': ['/api/health', '/api/explorer/data', '/api/db/accounts']
    })


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })
"""
flask_explorer_routes.py
────────────────────────
Paste these routes into your existing app.py (after your imports / helpers).

They serve the snaptrade_full_export.json file produced by
snaptrade_export_all.py, and expose a trigger endpoint so an admin
can refresh the export on demand from the UI.
"""

import subprocess
import threading

EXPORT_FILE = os.path.join(ACCOUNT_DATA_DIR, "snaptrade_full_export.json")


# ─────────────────────────────────────────────────────────────────────────────
# GET  /api/explorer/data
# Returns the entire multi-user export as JSON.
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/explorer/data", methods=["GET"])
@require_basic_auth
def explorer_get_data():
    # user = get_current_user()
    # if not user:
    #     return jsonify({"success": False, "error": "Not authenticated"}), 401

    data = _load_full_export()
    if not data:
        return jsonify({
            "success": False,
            "error": "No export file found. Run snaptrade_export_all.py first, "
                     "or hit POST /api/explorer/refresh."
        }), 404

    return jsonify({"success": True, "data": data})


# ─────────────────────────────────────────────────────────────────────────────
# POST /api/explorer/refresh
# Kicks off snaptrade_export_all.py in a background thread.
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/explorer/refresh", methods=["POST"])
@require_basic_auth
def explorer_refresh():
    user = get_current_user()
    # if not user:
        # return jsonify({"success": False, "error": "Not authenticated"}), 401

    def _run():
        try:
            subprocess.run(["python", "snaptrade_export_all.py"], timeout=120, check=True)
            print("[explorer] Export done, syncing to DB...")
            with app.app_context():
                sync_export_to_db(verbose=True)
            print("[explorer] DB sync complete.")
        except Exception as exc:
            print(f"[explorer] Refresh/sync failed: {exc}")

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"success": True, "message": "Export + DB sync started in background."})

# ─────────────────────────────────────────────────────────────────────────────
# GET /api/explorer/meta
# Quick metadata: last exported time + list of usernames.
# ─────────────────────────────────────────────────────────────────────────────
@app.route("/api/explorer/meta", methods=["GET"])
@require_basic_auth
def explorer_meta():
    # user = get_current_user()
    # if not user:
    #     return jsonify({"success": False, "error": "Not authenticated"}), 401

    data = _load_full_export()
    if not data:
        return jsonify({"success": True, "data": {"exported_at": None, "users": []}})

    users_meta = [
        {
            "username": u.get("username"),
            "exported_at": u.get("exported_at"),
            "account_count": len(u.get("accounts", [])),
        }
        for u in data.get("users", [])
    ]
    return jsonify({
        "success": True,
        "data": {
            "exported_at": data.get("exported_at"),
            "total_users": data.get("total_users", len(users_meta)),
            "users": users_meta,
        },
    })
@app.route('/api/export/account-data', methods=['GET'])
def export_account_data():
    """Export all account data as JSON"""
    try:
        account_id = get_account_id()
        if not account_id:
            return jsonify({'success': False, 'error': 'No account found'}), 400
        
        # Get all account data
        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        accounts_response = snaptrade_client.account_information.list_user_accounts(
            user_id=user_id,
            user_secret=user_secret
        )
        
        positions = get_portfolio_positions()
        summary = get_portfolio_summary().json.get('data', {}) if get_portfolio_summary() else {}
        
        # Get Snaptrade reporting data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=365)
        reporting_data = None
        try:
            reporting_response = snaptrade_client.transactions_and_reporting.get_reporting_custom_range(
                user_id=user_id,
                user_secret=user_secret,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )
            reporting_data = reporting_response.body if reporting_response.body else None
        except Exception as e:
            print(f"Error fetching reporting data: {e}")
        
        export_data = {
            'exportDate': datetime.now().isoformat(),
            'accountId': account_id,
            'accounts': accounts_response.body if accounts_response.body else [],
            'positions': positions,
            'summary': summary,
            'snaptradeReporting': reporting_data,
            'dataSource': 'Snaptrade API',
            'note': 'This data is from your connected Snaptrade account (Alpaca Paper)'
        }
        
        return jsonify({'success': True, 'data': export_data})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

# ── PostgreSQL table endpoints ─────────────────────────────────────────────

@app.route("/api/db/positions", methods=["GET"])
@require_basic_auth
def db_positions():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    rows = (
        db.session.query(Position, Account, User)
        .join(Account, Position.account_id == Account.id)
        .join(User, Account.user_id == User.id)
        .all()
    )
    return jsonify({"success": True, "data": [
        {
            "username": u.username,
            "account": a.name,
            "symbol": p.symbol,
            "description": p.description,
            "exchange": p.exchange,
            "asset_type": p.asset_type,
            "quantity": p.quantity,
            "price": p.price,
            "avg_cost": p.avg_cost,
            "market_value": p.market_value,
            "open_pnl": p.open_pnl,
        }
        for p, a, u in rows
    ]})

@app.route("/api/db/orders", methods=["GET"])
@require_basic_auth
def db_orders():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    rows = (
        db.session.query(Order, Account, User)
        .join(Account, Order.account_id == Account.id)
        .join(User, Account.user_id == User.id)
        .all()
    )
    return jsonify({"success": True, "data": [
        {
            "username": u.username,
            "account": a.name,
            "symbol": o.symbol,
            "side": o.side,
            "order_type": o.order_type,
            "quantity": o.quantity,
            "filled_quantity": o.filled_quantity,
            "price": o.price,
            "status": o.status,
            "time_in_force": o.time_in_force,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "filled_at": o.filled_at.isoformat() if o.filled_at else None,
        }
        for o, a, u in rows
    ]})

@app.route("/api/db/activities", methods=["GET"])
@require_basic_auth
def db_activities():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    rows = (
        db.session.query(Activity, Account, User)
        .join(Account, Activity.account_id == Account.id)
        .join(User, Account.user_id == User.id)
        .all()
    )
    return jsonify({"success": True, "data": [
        {
            "username": u.username,
            "account": a.name,
            "trade_date": act.trade_date.isoformat() if act.trade_date else None,
            "type": act.activity_type,
            "symbol": act.symbol,
            "description": act.description,
            "amount": act.amount,
            "units": act.units,
            "price": act.price,
            "fee": act.fee,
        }
        for act, a, u in rows
    ]})

@app.route("/api/db/accounts", methods=["GET"])
@require_basic_auth
def db_accounts():
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    rows = (
        db.session.query(Account, User)
        .join(User, Account.user_id == User.id)
        .all()
    )
    return jsonify({"success": True, "data": [
        {
            "username": u.username,
            "account_id": a.account_id,
            "name": a.name,
            "number": a.number,
            "institution": a.institution,
            "type": a.account_type,
            "status": a.status,
            "is_paper": a.is_paper,
            "currency": a.currency,
            "cash": a.cash,
            "buying_power": a.buying_power,
        }
        for a, u in rows
    ]})

@app.route("/api/db/sync", methods=["POST"])
@require_basic_auth
def db_sync_endpoint():
    """Manually trigger a DB sync from the existing JSON export."""
    user = get_current_user()
    if not user:
        return jsonify({"success": False, "error": "Not authenticated"}), 401
    try:
        stats = sync_export_to_db(verbose=True)
        return jsonify({"success": True, "stats": stats})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
        
if __name__ == '__main__':
    app.run(debug=True, port=5001)


