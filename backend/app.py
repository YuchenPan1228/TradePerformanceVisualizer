from flask import Flask, jsonify, request, session
from flask_cors import CORS
import os
from datetime import datetime, timedelta
from snaptrade_client import SnapTrade
import json
import yfinance as yf
import logging
import hashlib
import secrets

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True)

# User database file
USERS_DB_FILE = 'users.json'

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
    """Get SnapTrade client for current user"""
    user = get_current_user()
    if user:
        return SnapTrade(
            client_id=user['snaptrade_client_id'],
            consumer_key=user['snaptrade_consumer_key']
        )
    return None

def get_user_credentials():
    """Get user credentials for current user"""
    user = get_current_user()
    if user:
        return user['snaptrade_user_id'], user['snaptrade_user_secret']
    return None, None

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
        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return None
        
        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return None
            
        accounts_response = snaptrade_client.account_information.list_user_accounts(
            user_id=user_id,
            user_secret=user_secret
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

        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return []

        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return []

        positions_response = snaptrade_client.account_information.get_user_account_positions(
            user_id=user_id,
            user_secret=user_secret,
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


@app.route('/api/auth/register', methods=['POST'])
def register():
    """Register a new user account"""
    try:
        data = request.get_json()
        username = data.get('username', '').strip()
        password = data.get('password', '').strip()
        snaptrade_client_id = data.get('snaptrade_client_id', '').strip()
        snaptrade_consumer_key = data.get('snaptrade_consumer_key', '').strip()
        snaptrade_user_id = data.get('snaptrade_user_id', '').strip()
        snaptrade_user_secret = data.get('snaptrade_user_secret', '').strip()
        
        if not all([username, password, snaptrade_client_id, snaptrade_consumer_key, snaptrade_user_id, snaptrade_user_secret]):
            return jsonify({'success': False, 'error': 'All fields are required'}), 400
        
        users = load_users()
        if username in users:
            return jsonify({'success': False, 'error': 'Username already exists'}), 400
        
        # Verify Snaptrade credentials by trying to connect
        try:
            test_client = SnapTrade(
                client_id=snaptrade_client_id,
                consumer_key=snaptrade_consumer_key
            )
            # Try to list accounts to verify credentials
            test_client.account_information.list_user_accounts(
                user_id=snaptrade_user_id,
                user_secret=snaptrade_user_secret
            )
        except Exception as e:
            return jsonify({'success': False, 'error': f'Invalid Snaptrade credentials: {str(e)}'}), 400
        
        # Save user
        users[username] = {
            'username': username,
            'password_hash': hash_password(password),
            'snaptrade_client_id': snaptrade_client_id,
            'snaptrade_consumer_key': snaptrade_consumer_key,
            'snaptrade_user_id': snaptrade_user_id,
            'snaptrade_user_secret': snaptrade_user_secret,
            'created_at': datetime.now().isoformat()
        }
        save_users(users)
        
        return jsonify({'success': True, 'message': 'Account created successfully'})
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

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get user accounts"""
    try:
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
        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        snaptrade_client = get_snaptrade_client()
        if not snaptrade_client:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        # Note: Newer SDK versions deprecate account_id kwarg. Call without it.
        activities_response = snaptrade_client.transactions_and_reporting.get_activities(
            user_id=user_id,
            user_secret=user_secret
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
                
                # Extract name from nested symbol structure
                name = sym  # Default to symbol
                symbol_obj = position.get('symbol')
                if isinstance(symbol_obj, dict):
                    # Try to get description from nested structure
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
    """Return historical portfolio values - prefer daily reconstruction, fallback to Snaptrade weekly data"""
    try:
        if not get_current_user():
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        days = int(request.args.get('days', 30))
        use_daily = request.args.get('daily', 'true').lower() == 'true'
        selected_symbols = request.args.get('symbols', '').split(',') if request.args.get('symbols') else []
        selected_symbols = [s.strip().upper() for s in selected_symbols if s.strip()]
        
        # Try daily reconstruction first (more accurate)
        if use_daily:
            try:
                account_id = get_account_id()
                if account_id:
                    positions = get_portfolio_positions()
                    if positions:
                        # Reconstruct daily from individual stocks
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=days)
                        
                        # Filter by selected symbols if provided
                        if selected_symbols:
                            positions = [p for p in positions if _get_symbol_from_position(p) in selected_symbols]
                        
                        daily_values = {}
                        symbol_quantities = {}
                        
                        for position in positions:
                            sym = _get_symbol_from_position(position)
                            if sym and sym != 'N/A':
                                quantity = position.get('units', 0)
                                if quantity > 0:
                                    symbol_quantities[sym] = symbol_quantities.get(sym, 0) + quantity
                        
                        # Fetch daily prices for each symbol
                        for symbol, quantity in symbol_quantities.items():
                            try:
                                ticker = yf.Ticker(symbol)
                                hist = ticker.history(start=start_date, end=end_date, auto_adjust=True, interval='1d')
                                if hist is not None and len(hist) > 0:
                                    for date, row in hist.iterrows():
                                        date_str = date.strftime('%Y-%m-%d')
                                        price = float(row.get('Adj Close', row.get('Close', 0)))
                                        if date_str not in daily_values:
                                            daily_values[date_str] = 0
                                        daily_values[date_str] += price * quantity
                            except Exception as e:
                                print(f"Error fetching daily data for {symbol}: {e}")
                        
                        if daily_values:
                            history = [{'date': date, 'value': value} for date, value in sorted(daily_values.items())]
                            return jsonify({'success': True, 'data': history, 'source': 'daily_reconstruction'})
            except Exception as e:
                print(f"Daily reconstruction failed, falling back: {e}")
        
        # Fallback to Snaptrade weekly data
        account_id = get_account_id()
        if not account_id:
            # Fallback to synthetic if no account
            summary = get_portfolio_summary().json
            total_value = summary.get('data', {}).get('totalValue', 0) if summary else 0
            history = generate_history(total_value, days)
            return jsonify({'success': True, 'data': history})
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            user_id, user_secret = get_user_credentials()
            if not user_id or not user_secret:
                raise Exception('Not authenticated')
            
            snaptrade_client = get_snaptrade_client()
            if not snaptrade_client:
                raise Exception('Not authenticated')
            
            # Try get_reporting_custom_range for historical portfolio data
            reporting_response = snaptrade_client.transactions_and_reporting.get_reporting_custom_range(
                user_id=user_id,
                user_secret=user_secret,
                start_date=start_date.strftime('%Y-%m-%d'),
                end_date=end_date.strftime('%Y-%m-%d')
            )
            
            if reporting_response.body:
                # Process the reporting data to extract portfolio values over time
                history = []
                reporting_data = reporting_response.body
                
                # Snaptrade returns data in totalEquityTimeframe array
                if isinstance(reporting_data, dict) and 'totalEquityTimeframe' in reporting_data:
                    time_series = reporting_data.get('totalEquityTimeframe', [])
                    for entry in time_series:
                        if 'date' in entry and 'value' in entry:
                            history.append({
                                'date': entry['date'],
                                'value': float(entry.get('value', 0))
                            })
                # Fallback: check for other possible structures
                elif isinstance(reporting_data, dict) and 'data' in reporting_data:
                    time_series = reporting_data.get('data', [])
                    for entry in time_series:
                        if 'date' in entry and 'total_value' in entry:
                            history.append({
                                'date': entry['date'],
                                'value': float(entry.get('total_value', 0))
                            })
                        elif 'date' in entry and 'value' in entry:
                            history.append({
                                'date': entry['date'],
                                'value': float(entry.get('value', 0))
                            })
                
                if history:
                    # Sort by date to ensure chronological order
                    history.sort(key=lambda x: x['date'])
                    return jsonify({'success': True, 'data': history})
        except Exception as e:
            print(f"Error fetching Snaptrade reporting data: {e}")
        
        # Try get_user_account_return_rates as alternative
        try:
            user_id, user_secret = get_user_credentials()
            if not user_id or not user_secret:
                raise Exception('Not authenticated')
            
            snaptrade_client = get_snaptrade_client()
            if not snaptrade_client:
                raise Exception('Not authenticated')
            
            return_rates_response = snaptrade_client.account_information.get_user_account_return_rates(
                user_id=user_id,
                user_secret=user_secret,
                account_id=account_id
            )
            
            if return_rates_response.body:
                # Process return rates to build historical portfolio values
                rates_data = return_rates_response.body
                current_summary = get_portfolio_summary().json
                current_value = current_summary.get('data', {}).get('totalValue', 0) if current_summary else 0
                
                # If we have return rates, we can calculate historical values
                if isinstance(rates_data, dict) and 'data' in rates_data:
                    history = []
                    # Build history backwards from current value using return rates
                    # This is a simplified approach - adjust based on actual API response structure
                    for i in range(days):
                        day = end_date - timedelta(days=(days - 1 - i))
                        # Use current value as base (in real implementation, would use actual historical rates)
                        history.append({
                            'date': day.strftime('%Y-%m-%d'),
                            'value': current_value  # Placeholder - would need actual historical data
                        })
                    
                    if history:
                        return jsonify({'success': True, 'data': history})
        except Exception as e:
            print(f"Error fetching Snaptrade return rates: {e}")
        
        # Fallback to synthetic data based on current portfolio value
        summary = get_portfolio_summary().json
        total_value = summary.get('data', {}).get('totalValue', 0) if summary else 0
        history = generate_history(total_value, days)
        return jsonify({'success': True, 'data': history})
        
    except Exception as e:
        print(f"Error in get_portfolio_history: {e}")
        # Final fallback
        return jsonify({'success': True, 'data': generate_history(10000, 180)})


@app.route('/api/benchmark/history', methods=['GET'])
def get_benchmark_history():
    """Get historical data for benchmark (market index like SPY) with dividend-adjusted prices"""
    try:
        symbol = request.args.get('symbol', 'SPY').upper()
        days = int(request.args.get('days', 180))
        
        # Fetch historical data using yfinance
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            ticker = yf.Ticker(symbol)
            # Use auto_adjust=True to get dividend-adjusted prices
            hist = ticker.history(start=start_date, end=end_date, auto_adjust=True, interval='1d')
            
            if hist is not None and len(hist) > 0:
                history = []
                for date, row in hist.iterrows():
                    # Use Adj Close which includes dividend adjustments
                    # If auto_adjust=True, Close and Adj Close should be the same
                    price = float(row.get('Adj Close', row.get('Close', 0)))
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


@app.route('/api/portfolio/daily', methods=['GET'])
def get_daily_portfolio():
    """Reconstruct daily portfolio values from individual stock prices"""
    try:
        if not get_current_user():
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        account_id = get_account_id()
        if not account_id:
            return jsonify({'success': False, 'error': 'No account found'}), 400
        
        days = int(request.args.get('days', 30))
        selected_symbols = request.args.get('symbols', '').split(',') if request.args.get('symbols') else []
        selected_symbols = [s.strip().upper() for s in selected_symbols if s.strip()]
        
        # Get current positions
        positions = get_portfolio_positions()
        if not positions:
            return jsonify({'success': False, 'error': 'No positions found'}), 400
        
        # Filter by selected symbols if provided
        if selected_symbols:
            positions = [p for p in positions if _get_symbol_from_position(p) in selected_symbols]
        
        # Get date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        # Build daily portfolio reconstruction
        daily_values = {}
        stock_data = {}
        
        # First, get all unique symbols and their quantities
        symbol_quantities = {}
        for position in positions:
            sym = _get_symbol_from_position(position)
            if sym and sym != 'N/A':
                quantity = position.get('units', 0)
                if quantity > 0:
                    symbol_quantities[sym] = symbol_quantities.get(sym, 0) + quantity
        
        # Fetch daily prices for each symbol
        for symbol, quantity in symbol_quantities.items():
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date, auto_adjust=True, interval='1d')
                if hist is not None and len(hist) > 0:
                    for date, row in hist.iterrows():
                        date_str = date.strftime('%Y-%m-%d')
                        price = float(row.get('Adj Close', row.get('Close', 0)))
                        if date_str not in daily_values:
                            daily_values[date_str] = 0
                        daily_values[date_str] += price * quantity
                    stock_data[symbol] = {
                        'quantity': quantity,
                        'prices': {date.strftime('%Y-%m-%d'): float(row.get('Adj Close', row.get('Close', 0))) 
                                  for date, row in hist.iterrows()}
                    }
            except Exception as e:
                print(f"Error fetching data for {symbol}: {e}")
        
        # Convert to sorted list
        history = [{'date': date, 'value': value} for date, value in sorted(daily_values.items())]
        
        return jsonify({
            'success': True,
            'data': history,
            'stockData': stock_data,
            'symbols': list(symbol_quantities.keys())
        })
        
    except Exception as e:
        print(f"Error in get_daily_portfolio: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


def _get_symbol_from_position(position):
    """Extract symbol from position object"""
    sym = position.get('symbol')
    if isinstance(sym, dict):
        # Handle nested symbol structure
        inner_symbol = sym.get('symbol')
        if isinstance(inner_symbol, dict):
            # Sometimes symbol.symbol is also a dict
            return inner_symbol.get('symbol') or inner_symbol.get('raw_symbol') or 'N/A'
        return inner_symbol or sym.get('raw_symbol') or 'N/A'
    return str(sym) if sym else 'N/A'


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


if __name__ == '__main__':
    app.run(debug=True, port=5001)


