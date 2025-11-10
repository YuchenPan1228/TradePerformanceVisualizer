from flask import Flask, jsonify, request
from flask_cors import CORS
import os
from datetime import datetime, timedelta
from snaptrade_client import SnapTrade
import json
import yfinance as yf
import logging

app = Flask(__name__)
CORS(app)

# Initialize SnapTrade client
snaptrade = SnapTrade(
    client_id="CORNELL-UNIVERSITY-RESEARCH-TEST-ICBSL",
    consumer_key="bKh7Iq0NKEu0sdmEZEdzhbKsucQXffLLomqJTBEjQPCasweaJA"
)

# User credentials
USER_ID = "yuchen-user-1280"
# WARNING: Do not commit secrets in production
USER_SECRET = "2f5cb3b6-a796-44fd-9eae-0dfa5a8c005e"

WATCHLIST = [
    'AAPL','MSFT','GOOGL','AMZN','NVDA','META','TSLA','BRK.B','JPM','V',
    'XOM','UNH','JNJ','PG',
    'SPY','QQQ','VOO','VTI','IWM','DIA'
]
QUOTE_CACHE = {}
QUOTE_TTL_SECONDS = 60
USE_YAHOO = (os.getenv('USE_YAHOO', '0') == '1')

# Reduce noisy yfinance logging
try:
    logging.getLogger('yfinance').setLevel(logging.ERROR)
except Exception:
    pass
NOTIFICATIONS = []

def generate_history(total_value: float, days: int = 180):
    series = []
    base = float(total_value or 0)
    for i in range(days):
        t = i / max(days - 1, 1)
        drift = (t - 0.5) * 0.08 * base
        noise = (os.urandom(1)[0] / 255.0 - 0.5) * 0.02 * base
        val = max(0, base + drift + noise)
        day = datetime.now() - timedelta(days=(days - 1 - i))
        series.append({
            'date': day.strftime('%Y-%m-%d'),
            'value': round(val, 2)
        })
    return series


def get_account_id():
    """Get the first account ID for the user"""
    try:
        accounts_response = snaptrade.account_information.list_user_accounts(
            user_id=USER_ID,
            user_secret=USER_SECRET
        )
        if accounts_response.body:
            return accounts_response.body[0]['id']
        return None
    except Exception as e:
        print(f"Error getting account ID: {e}")
        return None


def get_portfolio_positions():
    """Get all positions for the user's account"""
    try:
        account_id = get_account_id()
        if not account_id:
            return []

        positions_response = snaptrade.account_information.get_user_account_positions(
            user_id=USER_ID,
            user_secret=USER_SECRET,
            account_id=account_id
        )
        return positions_response.body if positions_response.body else []
    except Exception as e:
        print(f"Error getting positions: {e}")
        return []


@app.route('/api/portfolio/positions', methods=['GET'])
def get_positions():
    """Get portfolio positions"""
    try:
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
        positions = get_portfolio_positions()

        total_value = 0
        total_cost = 0
        holdings = []

        for position in positions:
            sym = position.get('symbol')
            if sym:
                current_price = position.get('price', 0)
                quantity = position.get('units', 0)
                avg_cost = position.get('average_purchase_price', 0)

                market_value = current_price * quantity
                cost_basis = avg_cost * quantity

                total_value += market_value
                total_cost += cost_basis

                # Normalize symbol/name if object
                if isinstance(sym, dict):
                    norm_symbol = sym.get('symbol') or sym.get('raw_symbol') or 'N/A'
                    norm_name = sym.get('description') or norm_symbol
                else:
                    norm_symbol = sym
                    norm_name = str(sym)

                holdings.append({
                    'symbol': norm_symbol,
                    'name': norm_name,
                    'price': current_price,
                    'quantity': quantity,
                    'marketValue': market_value,
                    'costBasis': cost_basis,
                    'change': ((current_price - avg_cost) / avg_cost * 100) if avg_cost > 0 else 0
                })

        total_gain_loss = total_value - total_cost
        total_return = (total_gain_loss / total_cost * 100) if total_cost > 0 else 0

        return jsonify({
            'success': True,
            'data': {
                'totalValue': total_value,
                'totalCost': total_cost,
                'totalGainLoss': total_gain_loss,
                'totalReturn': total_return,
                'holdings': holdings
            }
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get user accounts"""
    try:
        accounts_response = snaptrade.account_information.list_user_accounts(
            user_id=USER_ID,
            user_secret=USER_SECRET
        )

        return jsonify({
            'success': True,
            'data': accounts_response.body if accounts_response.body else []
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get recent transactions"""
    try:
        # Note: Newer SDK versions deprecate account_id kwarg. Call without it.
        activities_response = snaptrade.transactions_and_reporting.get_activities(
            user_id=USER_ID,
            user_secret=USER_SECRET
        )

        transactions = []
        body = getattr(activities_response, 'body', None) or []
        if body:
            for activity in body[:10]:  # Get last 10 transactions
                raw_symbol = activity.get('symbol')
                if isinstance(raw_symbol, dict):
                    norm_symbol = raw_symbol.get('symbol') or raw_symbol.get('raw_symbol') or 'N/A'
                else:
                    norm_symbol = raw_symbol or 'N/A'
                transactions.append({
                    'id': activity.get('id'),
                    'symbol': norm_symbol,
                    'type': activity.get('type', 'Unknown'),
                    'description': activity.get('description', ''),
                    'date': activity.get('trade_date', activity.get('settlement_date', '')),
                    'amount': activity.get('amount', 0),
                    'quantity': activity.get('quantity', 0),
                    'price': activity.get('price', 0),
                    'status': 'Success'
                })

        return jsonify({
            'success': True,
            'data': transactions
        })
    except Exception as e:
        print(f"Error getting transactions: {e}")
        # Be resilient: return empty transactions on error so UI stays functional
        return jsonify({
            'success': True,
            'data': []
        })


@app.route('/api/portfolio/history', methods=['GET'])
def get_portfolio_history():
    """Return synthetic historical portfolio values for charts"""
    try:
        summary = get_portfolio_summary().json
        total_value = 0
        if summary and summary.get('data'):
            total_value = summary['data'].get('totalValue', 0)
        days = int(request.args.get('days', 180))
        history = generate_history(total_value, days)
        return jsonify({'success': True, 'data': history})
    except Exception as e:
        return jsonify({'success': True, 'data': generate_history(10000, 180)})


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
    # Yahoo uses '-' instead of '.' for some tickers like BRK.B
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
        # Prefer lightweight price via recent history to avoid blocked endpoints
        hist = yf.Ticker(yn).history(period='5d', interval='1d', auto_adjust=False)
        if hist is not None and len(hist.index) > 0 and 'Close' in hist:
            closes = hist['Close'].dropna()
            if len(closes) >= 1:
                price = float(closes.iloc[-1])
            if len(closes) >= 2:
                prev_close = float(closes.iloc[-2])
    except Exception:
        pass
    # If still missing, attempt fast_info as a secondary source
    if price is None:
        try:
            fi = getattr(yf.Ticker(yn), 'fast_info', None) or {}
            price = fi.get('last_price') or fi.get('last_trade_price')
            prev_close = prev_close if prev_close is not None else fi.get('previous_close')
        except Exception:
            pass
    # Compute change percent or fallback
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
    """Fetch quotes with per-symbol lightweight history method, using cache first."""
    results = {}
    if not symbols:
        return results
    # Cap to limit rate exposure
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
    """Return a cached or live quote for a single symbol with graceful fallback"""
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
    """Return batched quotes for watchlist or provided symbols (comma separated)."""
    try:
        symbols_param = request.args.get('symbols')
        symbols = []
        if symbols_param:
            symbols = [s.upper().strip() for s in symbols_param.split(',') if s.strip()]
        else:
            symbols = WATCHLIST[:]
        # Try batch first
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


@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat()
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)


