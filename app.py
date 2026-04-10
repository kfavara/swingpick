"""
SwingPick - Daily Swing Trading Suggestions
Fetches S&P 500 stocks, analyzes with technical indicators, suggests swing trades.
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import requests

# Load environment variables
load_dotenv()

# Support both local .env and Streamlit Cloud secrets
def get_secret(key, default=None):
    """Get secret from Streamlit secrets or environment."""
    try:
        from streamlit import secrets
        if key in secrets:
            return secrets[key]
    except:
        pass
    return os.getenv(key, default)


# History file
HISTORY_FILE = os.path.join(os.path.dirname(__file__), 'trade_history.csv')


def load_trade_history():
    """Load trade history from CSV file."""
    if os.path.exists(HISTORY_FILE):
        try:
            df = pd.read_csv(HISTORY_FILE)
            return df.to_dict('records')
        except:
            return []
    return []


def save_trade_history(history):
    """Save trade history to CSV file."""
    # Ensure all records have a source field
    for trade in history:
        if 'source' not in trade:
            trade['source'] = 'manual'
    df = pd.DataFrame(history)
    df.to_csv(HISTORY_FILE, index=False)


def fetch_alpaca_history(start_date=None):
    """Fetch all filled orders from Alpaca and return as trade history."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return []
    
    headers = {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
    }
    
    # Get all filled orders
    all_orders = []
    page_token = None
    
    while True:
        url = 'https://paper-api.alpaca.markets/v2/orders?status=filled&limit=100'
        if page_token:
            url += f'&after={page_token}'
        
        try:
            r = requests.get(url, headers=headers)
            if r.status_code != 200:
                break
            orders = r.json()
            if not orders:
                break
            all_orders.extend(orders)
            
            # Check if there are more pages
            if len(orders) < 100:
                break
            page_token = orders[-1].get('id')
        except:
            break
    
    # Filter by start_date if provided
    if start_date:
        filtered_orders = []
        for order in all_orders:
            filled_at = order.get('filled_at', '')[:10]
            if filled_at >= start_date:
                filtered_orders.append(order)
        all_orders = filtered_orders
    
    # Convert to trade history format (match buys with sells)
    history = []
    buys = {}  # symbol -> list of buys
    
    # Sort orders by filled_at for proper FIFO matching
    all_orders.sort(key=lambda x: x.get('filled_at', ''))
    
    for order in all_orders:
        symbol = order['symbol']
        qty = float(order['qty'])
        price = float(order['filled_avg_price'])
        side = order['side']
        date = order['filled_at'][:10]  # Use filled_at, not created_at
        
        if side == 'buy':
            if symbol not in buys:
                buys[symbol] = []
            buys[symbol].append({'qty': qty, 'price': price, 'date': date})
        else:  # sell
            # Find matching buy
            if symbol in buys and buys[symbol]:
                buy = buys[symbol][0]
                pnl = (price - buy['price']) * qty
                pnl_pct = (price - buy['price']) / buy['price'] * 100
                history.append({
                    'ticker': symbol,
                    'buy_price': buy['price'],
                    'sell_price': price,
                    'qty': qty,
                    'buy_date': buy['date'],
                    'sell_date': date,
                    'pnl_dollars': pnl,
                    'pnl_pct': pnl_pct,
                    'source': 'alpaca'
                })
                # Update remaining buy qty
                buy['qty'] -= qty
                if buy['qty'] <= 0:
                    buys[symbol].pop(0)
    
    return history

# Alpaca URLs - use secrets in production
ALPACA_DATA_URL = 'https://data.alpaca.markets'
ALPACA_TRADING_URL = get_secret('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')

# Track which data source is being used
_data_source = 'unknown'


def get_alpaca_account():
    """Get Alpaca account info."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return None
    url = f"{ALPACA_TRADING_URL}/v2/account"
    headers = {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
    }
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None


def get_alpaca_positions():
    """Get current positions from Alpaca."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return []
    url = f"{ALPACA_TRADING_URL}/v2/positions"
    headers = {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
    }
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return []


def get_alpaca_orders():
    """Get open orders from Alpaca."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return []
    url = f"{ALPACA_TRADING_URL}/v2/orders?status=open"
    headers = {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
    }
    try:
        r = requests.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return []


def is_market_open():
    """Check if market is currently open (9:30 AM - 4:00 PM ET, Mon-Fri)."""
    from datetime import time
    import pytz
    
    # Get current time in Eastern
    et = pytz.timezone('US/Eastern')
    now = datetime.now(et)
    
    # Check if it's a weekday (Mon=0, Sun=6)
    if now.weekday() >= 5:  # Saturday or Sunday
        return False
    
    # Check if within market hours (9:30 AM - 4:00 PM ET)
    market_open = time(9, 30)
    market_close = time(16, 0)
    current_time = now.time()
    
    return market_open <= current_time < market_close


def place_alpaca_order(symbol, qty, side, order_type='market', limit_price=None):
    """Place an order with Alpaca."""
    # Check if market is open
    if not is_market_open():
        return {'error': 'Market is closed. Orders can only be placed during market hours (9:30 AM - 4:00 PM ET).'}
    
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return {'error': 'No API keys'}
    
    url = f"{ALPACA_TRADING_URL}/v2/orders"
    headers = {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY,
        'Content-Type': 'application/json'
    }
    
    order_data = {
        'symbol': symbol,
        'qty': str(qty),
        'side': side,
        'type': order_type,
        'time_in_force': 'day'
    }
    
    if limit_price:
        order_data['limit_price'] = str(limit_price)
    
    try:
        r = requests.post(url, json=order_data, headers=headers)
        if r.status_code in [200, 201]:
            return r.json()
        else:
            return {'error': r.text}
    except Exception as e:
        return {'error': str(e)}


def get_alpaca_bars(symbol, timeframe='1D', limit=100):
    """Fetch historical bar data from Alpaca."""
    global _data_source
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        return None
    
    url = f"{ALPACA_DATA_URL}/v2/stocks/{symbol}/bars"
    params = {
        'timeframe': timeframe,
        'limit': limit,
        'adjustment': 'split'
    }
    headers = {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
    }
    
    try:
        response = requests.get(url, params=params, headers=headers)
        if response.status_code == 200:
            data = response.json()
            if 'bars' in data and data['bars']:
                df = pd.DataFrame(data['bars'])
                df['Date'] = pd.to_datetime(df['t'])
                df.set_index('Date', inplace=True)
                df = df.rename(columns={'o': 'Open', 'h': 'High', 'l': 'Low', 'c': 'Close', 'v': 'Volume'})
                _data_source = 'Alpaca'
                return df[['Open', 'High', 'Low', 'Close', 'Volume']]
        return None
    except Exception as e:
        return None


def get_yfinance_bars(symbol, period="3mo"):
    """Fallback to yfinance if Alpaca fails."""
    global _data_source
    try:
        import yfinance as yf
        stock = yf.Ticker(symbol)
        df = stock.history(period=period)
        if not df.empty:
            df = df.rename(columns={'Open': 'Open', 'High': 'High', 'Low': 'Low', 'Close': 'Close', 'Volume': 'Volume'})
        _data_source = 'Yahoo Finance'
        return df
    except:
        return None


# Cache for stock data (60 second TTL)
_stock_cache = {}
_stock_cache_time = {}

def get_stock_bars(symbol):
    """Use Yahoo Finance with caching to avoid rate limits."""
    global _stock_cache, _stock_cache_time
    import time
    
    # Check cache
    now = time.time()
    if symbol in _stock_cache:
        if now - _stock_cache_time.get(symbol, 0) < 60:
            return _stock_cache[symbol]
    
    # Use Yahoo Finance - provides full historical data for free
    df = get_yfinance_bars(symbol)
    
    # Cache the result
    if df is not None:
        _stock_cache[symbol] = df
        _stock_cache_time[symbol] = now
    
    return df


def get_market_performance():
    """Get SPY performance for relative strength comparison."""
    try:
        spy = get_yfinance_bars("SPY")
        print(f"DEBUG SPY data: {type(spy)}, len={len(spy) if spy is not None else 'None'}")  # Debug
        if spy is not None and len(spy) >= 20:
            spy_price = spy['Close'].iloc[-1]
            spy_5d_ago = spy['Close'].iloc[-6] if len(spy) >= 6 else spy_price
            spy_20d_ago = spy['Close'].iloc[-21] if len(spy) >= 21 else spy_5d_ago
            spy_63d_ago = spy['Close'].iloc[-64] if len(spy) >= 64 else spy_20d_ago
            
            return {
                'change_5d': ((spy_price - spy_5d_ago) / spy_5d_ago) * 100,
                'change_20d': ((spy_price - spy_20d_ago) / spy_20d_ago) * 100,
                'change_3mo': ((spy_price - spy_63d_ago) / spy_63d_ago) * 100,
                'price': spy_price
            }
    except Exception as e:
        st.error(f"SPY fetch error: {e}")
        pass
    st.error("DEBUG: returning zeros for market_perf")
    return {'change_5d': 0, 'change_20d': 0, 'change_3mo': 0, 'price': 0}


def get_yfinance_price(symbol):
    """Get current/live price from Yahoo Finance with caching and fallback."""
    import time
    
    # Check cache first (cache for 60 seconds)
    cache_key = f"price_{symbol}"
    if cache_key in get_yfinance_price._cache:
        cached_time, cached_price = get_yfinance_price._cache[cache_key]
        if time.time() - cached_time < 60:
            return cached_price
    
    try:
        import yfinance as yf
        stock = yf.Ticker(symbol)
        # Get fast info - real-time during market hours
        info = stock.fast_info
        if info and hasattr(info, 'last_price') and info.last_price:
            price = info.last_price
            get_yfinance_price._cache[cache_key] = (time.time(), price)
            return price
        # Fallback to regular price
        price = stock.info.get('currentPrice') or stock.info.get('regularMarketPrice')
        if price:
            get_yfinance_price._cache[cache_key] = (time.time(), price)
        return price
    except:
        return None

# Initialize price cache
get_yfinance_price._cache = {}

# Page config
st.set_page_config(
    page_title="SwingPick",
    page_icon="📈",
    layout="wide"
)

# ============================================================
# AUTHENTICATION & CONFIG
# ============================================================

# API Keys - support both local dev and Streamlit Cloud
ALPACA_API_KEY = get_secret('APCA_API_KEY_ID') or os.getenv('APCA_API_KEY_ID')
ALPACA_SECRET_KEY = get_secret('APCA_API_SECRET_KEY') or get_secret('APCA_SECRET_KEY') or os.getenv('APCA_SECRET_KEY')
ALPACA_BASE_URL = get_secret('APCA_API_BASE_URL') or os.getenv('APCA_API_BASE_URL', 'https://paper-api.alpaca.markets')

# Auth credentials
APP_USERNAME = get_secret('APP_USERNAME', 'admin')
APP_PASSWORD = get_secret('APP_PASSWORD', '')

# Simple session-state auth
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

# Authentication check
if APP_PASSWORD:  # Only require auth if password is set
    if not st.session_state.authenticated:
        st.markdown("""
        <style>
        .auth-container {
            max-width: 400px;
            margin: 100px auto;
            padding: 40px;
            background-color: #161b22;
            border-radius: 10px;
            text-align: center;
        }
        </style>
        """, unsafe_allow_html=True)
        
        st.markdown('<div class="auth-container">', unsafe_allow_html=True)
        st.title("🔐 SwingPick")
        st.markdown("Please log in to access the app")
        
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        
        if st.button("Login"):
            if username == APP_USERNAME and password == APP_PASSWORD:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Invalid credentials")
        
        st.markdown('</div>', unsafe_allow_html=True)
        st.stop()
else:
    st.session_state.authenticated = True

# Auto-refresh every 15 minutes (900 seconds)
st.markdown('<meta http-equiv="refresh" content="900">', unsafe_allow_html=True)

# Custom CSS for modern look
st.markdown("""
<style>
    .main {
        background-color: #0e1117;
    }
    .stApp {
        background-color: #0e1117;
    }
    .title-text {
        font-size: 2.5rem;
        font-weight: 700;
        color: #ffffff;
    }
    .subtitle {
        color: #8b949e;
        font-size: 1rem;
    }
    .metric-card {
        background-color: #161b22;
        border-radius: 10px;
        padding: 15px;
        margin: 5px 0;
    }
    .pick-row {
        background-color: #161b22;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
        border-left: 4px solid #58a6ff;
    }
    .pick-row-bearish {
        border-left: 4px solid #f85149;
    }
    .signal-bull {
        color: #3fb950;
        font-weight: 600;
    }
    .signal-bear {
        color: #f85149;
        font-weight: 600;
    }
    .disclaimer {
        background-color: #1f2937;
        border-radius: 8px;
        padding: 15px;
        margin-top: 30px;
        font-size: 0.85rem;
        color: #8b949e;
    }
    .section-header {
        color: #ffffff;
        font-size: 1.3rem;
        font-weight: 600;
        margin-bottom: 15px;
    }
    div[data-testid="stMetricValue"] {
        font-size: 1.5rem;
    }
    /* Force enable all input fields */
    input, textarea, div[data-baseweb="input"] {
        pointer-events: auto !important;
        user-select: auto !important;
    }
</style>
""", unsafe_allow_html=True)


def get_sp500_tickers(limit=250):
    """Get popular tickers (hardcoded for reliability)."""
    # Hardcoded list of popular stocks (avoiding Wikipedia fetch which may fail on cloud)
    POPULAR_TICKERS = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'META', 'TSLA', 'BRK-B', 'JPM', 'JNJ', 'V', 'UNH', 'HD', 'PG', 'MA', 'DIS', 'PYPL', 'ADBE', 'NFLX', 'INTC', 'CRM', 'AMD', 'QCOM', 'TXN', 'AVGO', 'ORCL', 'IBM', 'CSCO', 'UBER', 'ABNB', 'COIN', 'SNOW', 'PLTR', 'SQ', 'SHOP', 'MELI', 'SEA', 'TOST', 'RIVN', 'LCID', 'NIO', 'XPEV', 'LI', 'BABA', 'JD', 'PDD', 'NTES', 'BIDU', 'BA', 'CAT', 'GS', 'MMM', 'HON', 'GE', 'WMT', 'COST', 'TMO', 'ABT', 'DHR', 'BMY', 'PFE', 'MRK', 'KO', 'PEP', 'MCD', 'NKE', 'SBUX', 'LMT', 'AXP', 'BLK', 'GS', 'MS', 'C', 'BAC', 'WFC', 'T', 'VZ', 'CMCSA', 'TMUS']
    return POPULAR_TICKERS[:limit]


def calculate_rsi(prices, period=14):
    """Calculate Relative Strength Index."""
    delta = prices.diff()
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    avg_gain = gain.rolling(window=period, min_periods=1).mean()
    avg_loss = loss.rolling(window=period, min_periods=1).mean()
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calculate_sma(prices, period):
    """Calculate Simple Moving Average."""
    return prices.rolling(window=period, min_periods=1).mean()


def calculate_atr(high, low, close, period=14):
    """Calculate Average True Range."""
    high_low = high - low
    high_close = np.abs(high - close.shift())
    low_close = np.abs(low - close.shift())
    
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period, min_periods=1).mean()
    return atr


def calculate_indicators(df):
    """Calculate all technical indicators for a stock."""
    if df.empty or len(df) < 20:
        return None
    
    close = df['Close']
    high = df['High']
    low = df['Low']
    volume = df['Volume']
    
    # Current values
    current_price = close.iloc[-1]
    prev_close = close.iloc[-2] if len(close) > 1 else current_price
    
    # Calculate indicators
    rsi_14 = calculate_rsi(close, 14).iloc[-1]
    sma_5 = calculate_sma(close, 5).iloc[-1]
    sma_20 = calculate_sma(close, 20).iloc[-1]
    sma_50 = calculate_sma(close, 50).iloc[-1] if len(close) >= 50 else sma_20
    sma_200 = calculate_sma(close, 200).iloc[-1] if len(close) >= 200 else sma_50
    avg_volume_20 = volume.rolling(window=20, min_periods=1).mean().iloc[-1]
    atr_14 = calculate_atr(high, low, close, 14).iloc[-1]
    
    # 52-week high/low (use last 252 trading days)
    high_52wk = high.tail(252).max() if len(high) >= 20 else high.max()
    low_52wk = low.tail(252).min() if len(low) >= 20 else low.min()
    
    # Distance from 52-week high (as percentage)
    pct_from_52wk_high = ((current_price - high_52wk) / high_52wk) * 100
    
    # Change metrics
    price_change_1d = ((current_price - prev_close) / prev_close) * 100
    price_change_5d = ((current_price - close.iloc[-6]) / close.iloc[-6]) * 100 if len(close) >= 6 else 0
    price_change_20d = ((current_price - close.iloc[-21]) / close.iloc[-21]) * 100 if len(close) >= 21 else 0
    price_change_3mo = ((current_price - close.iloc[-63]) / close.iloc[-63]) * 100 if len(close) >= 63 else price_change_20d
    
    # Consolidation detection (price within X% of recent average)
    volatility = atr_14 / current_price * 100  # ATR as % of price
    in_consolidation = volatility < 3  # Tight consolidation if ATR < 3%
    
    # Volume trend
    vol_ratio = volume.iloc[-1] / avg_volume_20 if avg_volume_20 > 0 else 1
    
    return {
        'price': current_price,
        'prev_close': prev_close,
        'change_1d': price_change_1d,
        'change_5d': price_change_5d,
        'change_20d': price_change_20d,
        'change_3mo': price_change_3mo,
        'rsi': rsi_14,
        'sma_5': sma_5,
        'sma_20': sma_20,
        'sma_50': sma_50,
        'sma_200': sma_200,
        'avg_volume_20': avg_volume_20,
        'atr': atr_14,
        'volume': volume.iloc[-1],
        'high_52wk': high_52wk,
        'low_52wk': low_52wk,
        'pct_from_52wk_high': pct_from_52wk_high,
        'in_consolidation': in_consolidation,
        'volatility': volatility,
        'vol_ratio': vol_ratio
    }


def score_stock(indicators, ticker, market_perf=None):
    """
    Score a stock based on MARK MINERVINI'S TEMPLATE criteria.
    
    Minervini's 8-Point Template:
    1. Stock at new 52-week high (or close to it)
    2. RS line at new high (vs market)
    3. Strong sector affiliation
    4. Strong volume inflow
    5. Tight consolidation (base) before breakout
    6. Explosive move beginning (price acceleration)
    7. Consecutive weekly closes above trendline
    8. Defying market (relative strength)
    """
    if not indicators or indicators['price'] < 5:  # Exclude penny stocks
        return None, None
    
    score = 0
    reasons = []
    signals = []
    
    price = indicators['price']
    rsi = indicators['rsi']
    sma_5 = indicators['sma_5']
    sma_20 = indicators['sma_20']
    sma_50 = indicators['sma_50']
    sma_200 = indicators.get('sma_200', sma_50)
    volume = indicators['volume']
    avg_volume = indicators['avg_volume_20']
    change_5d = indicators['change_5d']
    change_20d = indicators['change_20d']
    change_3mo = indicators.get('change_3mo', change_20d)
    atr = indicators['atr']
    high_52wk = indicators.get('high_52wk', price)
    pct_from_52wk_high = indicators.get('pct_from_52wk_high', 0)
    in_consolidation = indicators.get('in_consolidation', False)
    vol_ratio = indicators.get('vol_ratio', 1)
    
    # Volume filter - Minervini requires strong volume
    if volume < 500000:
        return None, None
    
    # Market performance for relative strength
    market_5d = market_perf.get('change_5d', 0) if market_perf else 0
    market_20d = market_perf.get('change_20d', 0) if market_perf else 0
    market_3mo = market_perf.get('change_3mo', 0) if market_perf else 0
    
    # ==== MINERVINI CRITERIA (100 points max) ====
    
    # 1. PRICE: At new 52-week high OR within 5% of it (25 pts)
    if pct_from_52wk_high >= -2:  # At high
        score += 25
        reasons.append(f"At 52-week high (${high_52wk:.2f})")
    elif pct_from_52wk_high >= -5:  # Within 5%
        score += 15
        reasons.append(f"Near 52-week high ({pct_from_52wk_high:.1f}%)")
    elif pct_from_52wk_high >= -10:  # Within 10%
        score += 5
        reasons.append(f"Within 10% of 52-week high")
    
    # 2. RELATIVE STRENGTH: Outperforming market (25 pts)
    rs_5d = change_5d - market_5d
    rs_20d = change_20d - market_20d
    rs_3mo = change_3mo - market_3mo
    
    if rs_3mo >= 20:  # Strong outperformance
        score += 25
        reasons.append(f"RS vs market: +{rs_3mo:.1f}% (3mo)")
    elif rs_3mo >= 10:
        score += 20
        reasons.append(f"RS vs market: +{rs_3mo:.1f}% (3mo)")
    elif rs_20d >= 5:
        score += 15
        reasons.append(f"RS vs market: +{rs_20d:.1f}% (20d)")
    elif rs_5d > 0:
        score += 10
        reasons.append(f"Outperforming market today")
    
    # 3. TREND: Price above key MAs (20 pts)
    if price > sma_50 and sma_50 > sma_200:
        score += 15
        reasons.append("Price > SMA50 > SMA200 (bullish structure)")
    elif price > sma_50:
        score += 10
        reasons.append("Price above 50-day MA")
    elif sma_5 > sma_20:
        score += 5
        reasons.append("Short-term bullish trend")
    
    # 4. VOLUME: Strong volume confirming move (15 pts)
    if vol_ratio >= 2.0:
        score += 15
        signals.append(f"VOLUME SURGE: {vol_ratio:.1f}x average!")
        reasons.append(f"Volume surge ({vol_ratio:.1f}x)")
    elif vol_ratio >= 1.5:
        score += 10
        reasons.append(f"Strong volume ({vol_ratio:.1f}x)")
    elif vol_ratio >= 1.2:
        score += 5
        reasons.append(f"Above average volume")
    
    # 5. MOMENTUM: Strong recent move (15 pts)
    if change_5d >= 5:
        score += 10
        reasons.append(f"Strong momentum: +{change_5d:.1f}% this week")
    elif change_5d > 0:
        score += 5
        reasons.append(f"Positive momentum")
    
    # Acceleration: bigger moves this week than last
    if len([change_5d, change_20d/4]) >= 2 and change_5d > change_20d/4:
        score += 5
        reasons.append("Price acceleration")
    
    # Calculate suggested trade parameters (Minervini-style)
    if score >= 0:
        # Stop loss at 7-8% below entry (classic Minervini)
        stop_loss = price * 0.92  # 8% stop
        target = price * 1.25  # 25% target (3:1 reward:risk)
        
        # Alternative: ATR-based
        atr_pct = atr / price
        if atr_pct < 0.03:  # Tight consolidation
            stop_loss = price - (atr * 2)
            target = price + (atr * 6)  # 3:1
        
        return score, {
            'ticker': ticker,
            'score': score,
            'price': price,
            'change_1d': indicators['change_1d'],
            'change_5d': change_5d,
            'change_20d': change_20d,
            'change_3mo': change_3mo,
            'rsi': rsi,
            'volume_ratio': vol_ratio,
            'sma_5': sma_5,
            'sma_20': sma_20,
            'sma_50': sma_50,
            'high_52wk': high_52wk,
            'pct_from_52wk_high': pct_from_52wk_high,
            'rs_3mo': rs_3mo,
            'stop_loss': stop_loss,
            'target': target,
            'atr': atr,
            'reasons': reasons,
            'signals': signals,
            'direction': 'bullish'
        }
    
    return None, None


def analyze_sell_signals(ticker, buy_price):
    """
    Analyze a stock for sell signals.
    Returns both take profit signals (when up) and stop loss signals (when down).
    """
    try:
        df = get_stock_bars(ticker)
        
        if df is None or df.empty or len(df) < 20:
            return None
        
        # Ensure buy_price is a number, not a string
        try:
            buy_price = float(buy_price)
        except (TypeError, ValueError):
            buy_price = 0
        
        if buy_price <= 0:
            return None
        
        close = df['Close']
        high = df['High']
        low = df['Low']
        
        current_price = close.iloc[-1]
        prev_close = close.iloc[-2] if len(close) > 1 else current_price
        
        # Calculate indicators
        rsi_14 = calculate_rsi(close, 14).iloc[-1]
        sma_5 = calculate_sma(close, 5).iloc[-1]
        sma_20 = calculate_sma(close, 20).iloc[-1]
        sma_50 = calculate_sma(close, 50).iloc[-1] if len(close) >= 50 else sma_20
        
        change_1d = ((current_price - prev_close) / prev_close) * 100
        change_5d = ((current_price - close.iloc[-6]) / close.iloc[-6]) * 100 if len(close) >= 6 else 0
        
        # Calculate P&L
        pnl_pct = ((current_price - buy_price) / buy_price) * 100
        pnl_dollars = current_price - buy_price
        
        # Initialize signals
        take_profit_signals = []
        stop_loss_signals = []
        
        # === TAKE PROFIT SIGNALS (price is UP) ===
        if pnl_pct >= 8:
            take_profit_signals.append(f"+{pnl_pct:.1f}% profit - Consider taking profits!")
        
        if pnl_pct >= 5 and pnl_pct < 8:
            take_profit_signals.append(f"+{pnl_pct:.1f}% - Good profit, may continue")
        
        # RSI overbought at profit
        if rsi_14 >= 75 and pnl_pct > 0:
            take_profit_signals.append(f"RSI very overbought ({rsi_14:.1f}) - Profit may be peaking")
        
        # === STOP LOSS SIGNALS (price is DOWN) ===
        if pnl_pct <= -5:
            stop_loss_signals.append(f"{pnl_pct:.1f}% loss - Stop loss threshold!")
        elif pnl_pct <= -3:
            stop_loss_signals.append(f"{pnl_pct:.1f}% loss - Getting risky")
        
        # Price below moving averages (bearish)
        if sma_5 < sma_20 and pnl_pct < 0:
            stop_loss_signals.append("Downtrend confirmed (SMA 5 < 20)")
        
        if current_price < sma_20 and pnl_pct < 0:
            stop_loss_signals.append("Below 20-day SMA")
        
        if current_price < sma_50 and pnl_pct < 0:
            stop_loss_signals.append("Below 50-day SMA - Major downtrend")
        
        # Negative momentum
        if change_5d < -5 and pnl_pct < 0:
            stop_loss_signals.append(f"Big weekly drop ({change_5d:.1f}%)")
        
        # RSI oversold but still at loss
        if rsi_14 < 35 and pnl_pct < -3:
            stop_loss_signals.append(f"RSI oversold ({rsi_14:.1f}) but still at loss")
        
        return {
            'ticker': ticker,
            'buy_price': buy_price,
            'current_price': current_price,
            'pnl_pct': pnl_pct,
            'pnl_dollars': pnl_dollars,
            'rsi': rsi_14,
            'sma_5': sma_5,
            'sma_20': sma_20,
            'sma_50': sma_50,
            'change_1d': change_1d,
            'change_5d': change_5d,
            'take_profit_signals': take_profit_signals,
            'stop_loss_signals': stop_loss_signals,
            'direction': 'sell'
        }
        
    except Exception as e:
        return None


@st.cache_data(ttl=3600)  # Cache for 1 hour
def scan_stocks(tickers):
    """Scan all tickers and return scored stocks."""
    global _data_source
    _data_source = 'unknown'
    results = []
    total = len(tickers)
    st.write(f"DEBUG: scan_stocks called with {len(tickers)} tickers")
    
    # Debug - show tickers list
    print(f"[DEBUG] Scanning {total} tickers: {tickers[:5]}")
    
    # Get market performance for relative strength comparison
    # DEBUG - use non-zero dummy to test
    market_perf = {'change_5d': 3.0, 'change_20d': 2.0, 'change_3mo': 5.0, 'price': 500.0}
    
    # Debug: print market performance
    st.write(f"DEBUG market_perf: {market_perf}")
    
    for i, ticker in enumerate(tickers):
        try:
            # Fetch data
            df = get_stock_bars(ticker)
            
            st.write(f"Checking {ticker}...")  # Debug - show each ticker
            if df is None or df.empty:
                continue
            
            # Calculate indicators
            indicators = calculate_indicators(df)
            
            # Score the stock with market performance
            score, pick = score_stock(indicators, ticker, market_perf)
            
            if score:
                st.write(f"✅ {ticker}: score={score}")
            else:
                st.write(f"❌ {ticker}: score={score}, price={indicators.get('price')}, vol={indicators.get('volume')}")  # Debug
            
            if pick:
                st.write(f"DEBUG adding {ticker} to results")  # Debug
                results.append(pick)
            else:
                st.write(f"DEBUG {ticker} score={score} - no pick")  # Debug
            
            # Update progress
            # Note: Progress tracking done in caller
            
        except Exception as e:
            import traceback
            st.error(f"ERROR {ticker}: {e} - {traceback.format_exc()}")
    
    # Sort by score descending (include all, even zero scores for debug)
    results.sort(key=lambda x: x.get('score', 0), reverse=True)
    st.write("DEBUG: scan_stocks returning " + str(len(results)) + " results")
    if results:
        st.write("First result: " + str(results[0]))
    return results[:50]  # Return more


def main():
    """Main app function."""
    
    # Header
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<p class="title-text">📈 SwingPick</p>', unsafe_allow_html=True)
        st.markdown('<p class="subtitle">Daily swing trade suggestions based on technical analysis</p>', unsafe_allow_html=True)
        
        # Show data source status
        st.caption("📡 Data: Yahoo Finance")
    with col2:
        st.markdown(f"<p style='text-align:right;color:#8b949e;'>{datetime.now().strftime('%B %d, %Y')}</p>", unsafe_allow_html=True)
    
    st.divider()
    
    # ===== TOTAL P&L DISPLAY (REALIZED + OPEN) - ALPACA ONLY =====
    # Always fetch directly from Alpaca
    realized_pnl = 0
    open_pnl = 0
    
    if ALPACA_API_KEY and ALPACA_SECRET_KEY:
        # Get realized P&L from filled orders
        alpaca_history = fetch_alpaca_history('2026-03-19')
        if alpaca_history:
            realized_pnl = sum(s['pnl_dollars'] for s in alpaca_history)
        
        # Get open P&L from current positions
        alpaca_positions = get_alpaca_positions()
        if alpaca_positions:
            for pos in alpaca_positions:
                try:
                    ticker = pos.get('symbol', '')
                    avg_cost = float(pos.get('avg_entry_price', 0))
                    current_price = get_yfinance_price(ticker)
                    if not current_price:
                        # Fallback to Alpaca's current_price
                        alpaca_price = pos.get('current_price')
                        if alpaca_price:
                            try:
                                current_price = float(alpaca_price)
                            except:
                                pass
                    qty = float(pos.get('qty', 0))
                    if ticker and current_price and avg_cost:
                        pnl = (current_price - avg_cost) * qty
                        open_pnl += pnl
                except:
                    pass
    
    realized_pnl_color = "#3fb950" if realized_pnl >= 0 else "#f85149"
    open_pnl_color = "#3fb950" if open_pnl >= 0 else "#f85149"
    
    # Combined total (realized + open)
    combined_pnl = realized_pnl + open_pnl
    combined_color = "#3fb950" if combined_pnl >= 0 else "#f85149"
    
    col_r, col_o, col_c = st.columns(3)
    with col_r:
        st.markdown(f"""
        <div style="background-color:#161b22;padding:15px;border-radius:10px;margin-bottom:20px;text-align:center;">
            <span style="font-size:0.9rem;color:#8b949e;">📊 Realized P&L (Closed Trades)</span><br>
            <span style="font-size:1.3rem;font-weight:700;color:{realized_pnl_color};">${realized_pnl:+,.2f}</span>
        </div>
        """, unsafe_allow_html=True)
    with col_o:
        st.markdown(f"""
        <div style="background-color:#161b22;padding:15px;border-radius:10px;margin-bottom:20px;text-align:center;">
            <span style="font-size:0.9rem;color:#8b949e;">📈 Open P&L (Current Positions)</span><br>
            <span style="font-size:1.3rem;font-weight:700;color:{open_pnl_color};">${open_pnl:+,.2f}</span>
        </div>
        """, unsafe_allow_html=True)
    with col_c:
        st.markdown(f"""
        <div style="background-color:#161b22;padding:15px;border-radius:10px;margin-bottom:20px;text-align:center;">
            <span style="font-size:0.9rem;color:#8b949e;">💰 Combined Total</span><br>
            <span style="font-size:1.5rem;font-weight:700;color:{combined_color};">${combined_pnl:+,.2f}</span>
        </div>
        """, unsafe_allow_html=True)
    
    # ===== PORTFOLIO TRACKING SECTION =====
    st.markdown('<p class="section-header">💼 My Positions</p>', unsafe_allow_html=True)
    
    # Get Alpaca account info
    account_info = get_alpaca_account()
    if account_info:
        try:
            cash = float(account_info.get('cash', 0))
            portfolio_value = float(account_info.get('portfolio_value', 0))
            st.caption(f"💰 Cash: ${cash:,.2f} | Portfolio: ${portfolio_value:,.2f}")
        except:
            pass
    
    # Auto-sync from Alpaca on page load (if not already done)
    if 'alpaca_synced' not in st.session_state:
        st.session_state.alpaca_synced = False
    
    # Sync button to fetch positions from Alpaca
    sync_button = st.button("🔄 Sync from Alpaca", key="sync_alpaca_btn")
    
    # Auto-sync on first load
    if not st.session_state.alpaca_synced and ALPACA_API_KEY and ALPACA_SECRET_KEY:
        sync_button = True
        st.session_state.alpaca_synced = True
    
    if sync_button:
        alpaca_positions = get_alpaca_positions()
        if alpaca_positions and len(alpaca_positions) > 0:
            # Clear and repopulate portfolio from Alpaca
            st.session_state.portfolio = []
            for pos in alpaca_positions:
                try:
                    # Get current price from Yahoo Finance (real-time during market hours)
                    ticker = pos.get('symbol', '')
                    current_price = get_yfinance_price(ticker)
                    # Fallback to Alpaca price if Yahoo fails
                    if not current_price:
                        current_price = float(pos.get('current_price', 0))
                    avg_cost = float(pos.get('avg_entry_price', 0))
                    qty = float(pos.get('qty', 0))
                    
                    if ticker:
                        st.session_state.portfolio.append({
                            'ticker': ticker,
                            'buy_price': avg_cost,
                            'current_price': current_price,
                            'qty': qty,
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'alpaca_position': True
                        })
                except:
                    pass
            if not st.session_state.alpaca_synced:  # Only show on auto-sync
                st.success(f"Synced {len(st.session_state.portfolio)} positions from Alpaca")
                st.session_state.alpaca_synced = True
            st.rerun()
        else:
            st.info("No positions found in Alpaca account")
    
    # Show open orders
    open_orders = get_alpaca_orders()
    if open_orders and len(open_orders) > 0:
        st.markdown("**📋 Open Orders (Waiting to Fill)**")
        for order in open_orders:
            with st.container():
                side_color = "#3fb950" if order.get('side') == 'buy' else "#f85149"
                st.markdown(f"""
                <div class="pick-row" style="border-left: 4px solid {side_color};">
                    <div style="display:flex;justify-content:space-between;align-items:center;">
                        <div>
                            <span style="font-size:1.1rem;font-weight:700;color:#ffffff;">{order.get('symbol')}</span>
                            <span style="color:{side_color};margin-left:10px;">{order.get('side').upper()}</span>
                            <span style="color:#8b949e;margin-left:10px;">{order.get('qty')} shares</span>
                        </div>
                        <span style="color:#8b949e;">{order.get('type').upper()} - {order.get('time_in_force')}</span>
                    </div>
                    <div style="margin-top:5px;">
                        <span style="color:#8b949e;">Limit: ${order.get('limit_price', 'Market')}</span>
                        <span style="color:#8b949e;margin-left:15px;">Status: {order.get('status')}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
        st.caption("Open orders will fill when market price hits your limit (or immediately for market orders)")
    
    # Initialize sold_history from Alpaca only
    if 'sold_history' not in st.session_state:
        # Fetch directly from Alpaca
        alpaca_history = fetch_alpaca_history('2026-03-19')
        if alpaca_history:
            st.session_state.sold_history = alpaca_history
        else:
            st.session_state.sold_history = []
    
    # NOTE: sold_history now persists between page reloads
    # To manually clear, use the "Clear History" button below
    
    
    # Add new position form - Alpaca only
    st.markdown("**🟢 Buy via Alpaca**")
    col1, col2, col3 = st.columns([2, 2, 2])
    with col1:
        new_ticker = st.text_input("Ticker", placeholder="AAPL", key="buy_ticker").upper()
    with col2:
        qty = st.number_input("Quantity", min_value=1, step=1, value=1, key="buy_qty")
    with col3:
        use_market = st.checkbox("Market Order", value=True, key="buy_market")
    
    alpaca_buy_button = st.button("📈 Place Buy Order", type="primary", use_container_width=True)
    
    # Handle Alpaca buy
    if alpaca_buy_button and new_ticker and qty:
        order = place_alpaca_order(new_ticker, qty, 'buy', 'market' if use_market else 'limit')
        if 'error' in order:
            st.error(f"Order failed: {order['error']}")
        else:
            st.success(f"✅ Buy order placed: {qty} share(s) of {new_ticker}")
            st.rerun()
    
    # ===== MY POSITIONS (ALPACA ONLY) =====
    # Display positions from Alpaca directly
    if ALPACA_API_KEY and ALPACA_SECRET_KEY:
        alpaca_positions = get_alpaca_positions()
        if alpaca_positions:
            st.markdown('<p class="section-header">💼 My Positions</p>', unsafe_allow_html=True)
            account_info = get_alpaca_account()
            if account_info:
                try:
                    cash = float(account_info.get('cash', 0))
                    portfolio_value = float(account_info.get('portfolio_value', 0))
                    st.caption(f"💰 Cash: ${cash:,.2f} | Portfolio: ${portfolio_value:,.2f}")
                except:
                    pass
            
            for pos in alpaca_positions:
                try:
                    ticker = pos.get('symbol', '')
                    avg_cost = float(pos.get('avg_entry_price', 0))
                    current_price = get_yfinance_price(ticker)
                    if not current_price:
                        # Fallback to Alpaca's current_price
                        alpaca_price = pos.get('current_price')
                        if alpaca_price:
                            try:
                                current_price = float(alpaca_price)
                            except:
                                pass
                    qty = float(pos.get('qty', 0))
                    
                    if ticker and current_price and current_price > 0:
                        pnl = (current_price - avg_cost) * qty
                        pnl_pct = (current_price - avg_cost) / avg_cost * 100 if avg_cost else 0
                        pnl_color = "#3fb950" if pnl >= 0 else "#f85149"
                        
                        # Try to get signals, but continue even if it fails
                        try:
                            sell_signals = analyze_sell_signals(ticker, avg_cost)
                        except Exception as sig_err:
                            st.warning(f"Could not get signals: {sig_err}")
                            sell_signals = None
                        # Always display this position
                        st.subheader(f"{ticker}")
                        c1, c2, c3, c4 = st.columns(4)
                        c1.metric("Avg Cost", f"${avg_cost:.2f}")
                        c2.metric("Current", f"${current_price:.2f}")
                        c3.metric("Qty", f"{qty:.0f}")
                        c4.metric("P&L", f"${pnl:+.2f}", f"{pnl_pct:+.2f}%")
                        
                        # Show signal
                        if sell_signals:
                            rsi_val = sell_signals.get('rsi')
                            change_val = sell_signals.get('change_1d')
                            if rsi_val:
                                st.write(f"RSI: {rsi_val:.1f} | Today: {change_val:+.2f}%" if change_val else f"RSI: {rsi_val:.1f}")
                            
                            take_profit = sell_signals.get('take_profit_signals', [])
                            stop_loss = sell_signals.get('stop_loss_signals', [])
                            
                            if take_profit:
                                st.success(f"✅ {'; '.join(take_profit)}")
                            elif stop_loss:
                                st.error(f"🛑 {'; '.join(stop_loss)}")
                        
                        # Always show HOLD if no signal
                        if not sell_signals or (not take_profit and not stop_loss):
                            st.info("➡️ HOLD")
                        
                        # Sell button
                        if st.button(f"🔴 Sell {ticker}", key=f"sell_{ticker}"):
                            order = place_alpaca_order(ticker, int(qty), 'sell', 'market')
                            if 'error' in order:
                                st.error(f"Order failed: {order['error']}")
                            else:
                                st.success(f"✅ Sell order placed: {int(qty)} share(s) of {ticker}")
                                st.rerun()
                        
                        st.divider()
                except Exception as e:
                    print(f"Error displaying {pos.get('symbol')}: {e}")
        else:
            st.info("No open positions in Alpaca")
        

    else:
        st.warning("Alpaca not configured")
    
    
    # ===== MARKET SCAN SECTION =====
    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        scan_button = st.button("🔄 Scan Market", type="primary", use_container_width=True)
    with col2:
        num_picks = st.slider("Number of picks to show", 5, 20, 10)
    
    # Initialize session state
    if 'results' not in st.session_state:
        st.session_state.results = []
    if 'last_scan' not in st.session_state:
        st.session_state.last_scan = None
    
    # Auto-scan if not done today
    today = datetime.now().date()
    last_scan_date = st.session_state.last_scan.date() if st.session_state.last_scan else None
    
    if last_scan_date != today and not st.session_state.results:
        # Auto-run scan on page load
        scan_button = True
    
    # Run scan
    st.write("DEBUG: About to check scan_button")  # Debug
    if scan_button:
        st.write("DEBUG: scan_button is True!")  # Debug
        try:
            progress_bar = st.progress(0)
            tickers = get_sp500_tickers(250)
            st.write(f"Scanning {len(tickers)} tickers: {tickers[:5]}")  # Debug
            results = scan_stocks(tickers)
            st.write(f"Found {len(results)} results")  # Debug
            st.session_state.results = results
            st.session_state.last_scan = datetime.now()
        except Exception as scan_err:
            st.error("Scan error: " + str(scan_err))
            print("Scan error:", scan_err)
        
        if last_scan_date != today:  # Only show success if auto-scanned
            if results:
                st.success(f"Found {len(results)} potential swing trades!")
            else:
                st.warning("No trades found. Try again later or check API limits.")
    
    # Display results
    if st.session_state.results:
        results = st.session_state.results[:num_picks]
        
        # Summary metrics
        st.markdown('<p class="section-header">📊 Today\'s Top Picks</p>', unsafe_allow_html=True)
        
        for i, pick in enumerate(results, 1):
            score = pick.get("score", 0)
            ticker = pick["ticker"]
            price = pick["price"]
            change = pick["change_1d"]
            st.subheader("{}. {} - ${:.2f} ({:+.2f}%)".format(i, ticker, price, change))
            m1, m2, m3, m4, m5, m6 = st.columns(6)
            m1.metric("Score", str(score))
            m2.metric("Stop", "${:.2f}".format(pick["stop_loss"]))
            m3.metric("Target", "${:.2f}".format(pick["target"]))
            rr = 0
            if pick.get("stop_loss"):
                rr = (pick["target"]-pick["price"])/(pick["price"]-pick["stop_loss"])
            m4.metric("R:R", "1:{:.1f}".format(rr))
            m5.metric("52W High", "{:.1f}%".format(pick.get("pct_from_52wk_high", 0)))
            m6.metric("RSI", str(pick.get("rsi", "N/A")))
            reasons = pick.get("reasons", [])
            if reasons:
                st.write("**Why:** " + ", ".join(reasons[:4]))
            st.divider()

    elif st.session_state.last_scan is None:
        st.info("👆 Click 'Scan Market' to analyze S&P 500 stocks and find swing trade opportunities.")
    
    # Disclaimer
    st.markdown("""
    <div class="disclaimer">
        <strong>⚠️ Disclaimer:</strong> This tool is for educational and informational purposes only. 
        It is not financial advice, trading advice, or any other form of professional advice. 
        Past performance does not guarantee future results. 
        Always do your own research before making any investment decisions. 
        Trade at your own risk.
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
