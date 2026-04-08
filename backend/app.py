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
import re
import glob

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(32))
CORS(app, supports_credentials=True, origins=['http://localhost:3000', 'http://localhost:3001', 'http://127.0.0.1:3000', 'http://127.0.0.1:3001', 'http://18.221.160.103:5001', 'http://18.221.160.103:3000', 'http://bfi.duckdns.org'])

# Configuration
SNAPTRADE_CLIENT_ID = "BFI-DFTUD"
SNAPTRADE_CONSUMER_KEY = "UflJTFaCJXSpEEmoGaEjtotESLszJnvFlXrglda7xlWRbAgb6y"

# Database files
USERS_DB_FILE = 'users.json'
ACCOUNT_DATA_DIR = 'data-export'
ACCOUNT_DATA_FILE = os.path.join(ACCOUNT_DATA_DIR, 'account-data.json')

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
        user = get_current_user()
        if not user:
            return None
        
        # Try to get from stored account data first
        account_data = load_account_data()
        user_accounts = account_data.get(user['username'], {}).get('accounts', [])
        if user_accounts and len(user_accounts) > 0:
            return user_accounts[0].get('id')
        
        # Otherwise fetch from Snaptrade
        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return None
        
        snaptrade_client = get_snaptrade_client()
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
        
        user_id = user.get('snaptrade_user_id')
        user_secret = user.get('snaptrade_user_secret')
        
        if not user_id or not user_secret:
            return jsonify({'success': False, 'error': 'Invalid user credentials'}), 400
        
        # Fetch account information from Snaptrade
        snaptrade_client = get_snaptrade_client()
        try:
            accounts_response = snaptrade_client.account_information.list_user_accounts(
                user_id=user_id,
                user_secret=user_secret
            )
            
            if not accounts_response.body:
                return jsonify({'success': False, 'error': 'No accounts found. Please connect your brokerage account first.'}), 400
            
            accounts = accounts_response.body
            
        except Exception as e:
            return jsonify({'success': False, 'error': f'Failed to fetch accounts: {str(e)}'}), 500
        
        # Fetch detailed account information for the first account
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
        
        # Store account data
        account_data = load_account_data()
        account_data[username] = {
            'username': username,
            'accounts': accounts,
            'primary_account': account_details,
            'fetched_at': datetime.now().isoformat()
        }
        save_account_data(account_data)
        
        # Update user status
        users[username]['account_connected'] = True
        users[username]['accounts_fetched_at'] = datetime.now().isoformat()
        save_users(users)
        
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

@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """Get user accounts"""
    try:
        user = get_current_user()
        if not user:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        # Try to get from stored account data first
        account_data = load_account_data()
        user_accounts = account_data.get(user['username'], {}).get('accounts', [])
        
        if user_accounts:
            return jsonify({
                'success': True,
                'data': user_accounts
            })
        
        # Otherwise fetch from Snaptrade
        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        snaptrade_client = get_snaptrade_client()
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

def _load_option_orders_from_latest_export():
    """Fallback: load option orders from latest full-export JSON file."""
    try:
        export_files = sorted(
            glob.glob(os.path.join('data-export', 'snaptrade_full_export_*.json')),
            key=os.path.getmtime,
            reverse=True
        )
        if not export_files:
            return []

        with open(export_files[0], 'r', encoding='utf-8') as f:
            payload = json.load(f)
        accounts = payload.get('accounts', []) if isinstance(payload, dict) else []
        rows = []
        for account in accounts:
            orders = account.get('orders', []) if isinstance(account, dict) else []
            for order in orders:
                option_symbol = order.get('option_symbol')
                if not isinstance(option_symbol, dict):
                    continue
                underlying = option_symbol.get('underlying_symbol')
                underlying_symbol = None
                if isinstance(underlying, dict):
                    underlying_symbol = underlying.get('symbol') or underlying.get('raw_symbol')
                option_type = (option_symbol.get('option_type') or '').upper()
                if option_type not in ('CALL', 'PUT'):
                    option_type = None
                action = (order.get('action') or '').upper()
                filled_qty = _to_float(order.get('filled_quantity', order.get('total_quantity', 0)), 0.0)
                total_qty = _to_float(order.get('total_quantity', filled_qty), filled_qty)
                qty_for_display = filled_qty if filled_qty > 0 else total_qty
                execution_price = _to_float(order.get('execution_price'), 0.0)
                limit_price = _to_float(order.get('limit_price'), 0.0)
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
                    'description': f"Order {(order.get('status') or 'UNKNOWN')}",
                    'priceFromDescription': None,
                    'date': order.get('time_executed') or order.get('time_placed') or '',
                    'tradeDate': order.get('time_executed'),
                    'settlementDate': None,
                    'amount': order_amount,
                    'fee': 0.0,
                    'netAmount': order_amount,
                    'quantity': qty_for_display,
                    'units': qty_for_display,
                    'price': execution_price,
                    'isOption': True,
                    'underlyingSymbol': underlying_symbol,
                    'strikePrice': _to_float(option_symbol.get('strike_price'), None),
                    'optionType': option_type,
                    'expirationDate': option_symbol.get('expiration_date'),
                    'contractCount': qty_for_display,
                    'positionSide': 'LONG' if 'BUY' in action else ('SHORT' if 'SELL' in action else None),
                    'limitPrice': limit_price,
                    'executionPrice': execution_price,
                    'placedTime': order.get('time_placed'),
                    'executedTime': order.get('time_executed'),
                    'feeBreakdown': {
                        'occClearingFee': 0.0,
                        'orfFee': 0.0,
                        'otherFees': 0.0
                    },
                    'status': order.get('status') or 'UNKNOWN',
                    'source': 'order'
                })
        return rows
    except Exception as export_err:
        print(f"Error loading option orders from export: {export_err}")
        return []

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    """Get recent transactions"""
    try:
        user_id, user_secret = get_user_credentials()
        if not user_id or not user_secret:
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        
        snaptrade_client = get_snaptrade_client()
        
        transactions = []
        activities_response = snaptrade_client.transactions_and_reporting.get_activities(
            user_id=user_id,
            user_secret=user_secret
        )
        activities_body = getattr(activities_response, 'body', None) or []
        option_activity_candidates = []
        if activities_body:
            for activity in activities_body:
                raw_symbol = activity.get('symbol')
                if isinstance(raw_symbol, dict):
                    norm_symbol = raw_symbol.get('symbol') or raw_symbol.get('raw_symbol') or 'N/A'
                else:
                    norm_symbol = raw_symbol or 'N/A'
                
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

        # Option orders from primary account only (stored first account / get_account_id).
        order_rows_added = 0
        account_id = get_account_id()
        if account_id:
            try:
                orders_response = snaptrade_client.account_information.get_user_account_orders(
                    user_id=user_id,
                    user_secret=user_secret,
                    account_id=account_id
                )
                orders_body = getattr(orders_response, 'body', None) or []
                for order in orders_body:
                    option_symbol = order.get('option_symbol')
                    if not isinstance(option_symbol, dict):
                        continue

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
                    side = 'BUY' if 'BUY' in action else ('SELL' if 'SELL' in action else None)

                    limit_price = _to_float(order.get('limit_price'), 0.0)
                    execution_price = _to_float(order.get('execution_price'), 0.0)
                    status_value = order.get('status') or 'UNKNOWN'
                    placed_time = order.get('time_placed')
                    executed_time = order.get('time_executed')
                    order_dt = _parse_iso_dt(executed_time or placed_time)
                    key = _option_key(option_type, _to_float(option_symbol.get('strike_price'), None), option_symbol.get('expiration_date'), underlying_symbol)
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
                    order_amount = execution_price * filled_qty * 100
                    if 'BUY' in action:
                        order_amount = -abs(order_amount)
                    elif 'SELL' in action:
                        order_amount = abs(order_amount)

                    transactions.append({
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
                    order_rows_added += 1
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
        
        # Return only the first 10 transactions
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
    """Return historical portfolio values"""
    try:
        if not get_current_user():
            return jsonify({'success': False, 'error': 'Not authenticated'}), 401
        days = int(request.args.get('days', 30))
        use_daily = request.args.get('daily', 'true').lower() == 'true'
        selected_symbols = request.args.get('symbols', '').split(',') if request.args.get('symbols') else []
        selected_symbols = [s.strip().upper() for s in selected_symbols if s.strip()]
        
        if use_daily:
            try:
                account_id = get_account_id()
                if account_id:
                    positions = get_portfolio_positions()
                    if positions:
                        end_date = datetime.now()
                        start_date = end_date - timedelta(days=days)
                        
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
        
        summary = get_portfolio_summary().json
        total_value = summary.get('data', {}).get('totalValue', 0) if summary else 0
        history = generate_history(total_value, days)
        return jsonify({'success': True, 'data': history})
        
    except Exception as e:
        print(f"Error in get_portfolio_history: {e}")
        return jsonify({'success': True, 'data': generate_history(10000, 180)})


@app.route('/api/benchmark/history', methods=['GET'])
def get_benchmark_history():
    """Get historical data for benchmark"""
    try:
        symbol = request.args.get('symbol', 'SPY').upper()
        days = int(request.args.get('days', 180))
        
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(start=start_date, end=end_date, auto_adjust=True, interval='1d')
            
            if hist is not None and len(hist) > 0:
                history = []
                for date, row in hist.iterrows():
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


def _get_symbol_from_position(position):
    """Extract symbol from position object"""
    sym = position.get('symbol')
    if isinstance(sym, dict):
        inner_symbol = sym.get('symbol')
        if isinstance(inner_symbol, dict):
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


