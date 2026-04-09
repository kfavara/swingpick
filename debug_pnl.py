import requests
import os

ALPACA_API_KEY = os.getenv('APCA_API_KEY_ID')
ALPACA_SECRET_KEY = os.getenv('APCA_SECRET_KEY')

headers = {
    'APCA-API-KEY-ID': ALPACA_API_KEY,
    'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY
}

# Get all filled orders
all_orders = []
page_token = None

print("Fetching all filled orders...")

while True:
    url = 'https://paper-api.alpaca.markets/v2/orders?status=filled&limit=100'
    if page_token:
        url += f'&after={page_token}'
    
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"Error: {r.status_code}")
        break
    orders = r.json()
    if not orders:
        break
    
    for o in orders:
        filled_at = o.get('filled_at', '')[:10]
        all_orders.append({
            'symbol': o['symbol'],
            'side': o['side'],
            'qty': float(o['qty']),
            'price': float(o['filled_avg_price']),
            'date': filled_at
        })
    
    if len(orders) < 100:
        break
    page_token = orders[-1].get('id')

print(f"Total orders: {len(all_orders)}")

# Filter after 2026-03-19
filtered = [o for o in all_orders if o['date'] >= '2026-03-19']
print(f"Orders from 3/19/2026: {len(filtered)}")

# Match buys with sells
buys = {}
trades = []

for order in filtered:
    symbol = order['symbol']
    qty = order['qty']
    price = order['price']
    side = order['side']
    date = order['date']
    
    if side == 'buy':
        if symbol not in buys:
            buys[symbol] = []
        buys[symbol].append({'qty': qty, 'price': price, 'date': date})
    else:  # sell
        if symbol in buys and buys[symbol]:
            buy = buys[symbol][0]
            pnl = (price - buy['price']) * qty
            trades.append({
                'ticker': symbol,
                'buy_price': buy['price'],
                'sell_price': price,
                'qty': qty,
                'pnl': pnl,
                'buy_date': buy['date'],
                'sell_date': date
            })
            buy['qty'] -= qty
            if buy['qty'] <= 0:
                buys[symbol].pop(0)

print("\n=== TRADES FROM ALPACA ===\n")
for t in trades:
    print(f"{t['buy_date']} Buy {t['ticker']} {t['qty']:.0f} @ ${t['buy_price']:.2f}")
    print(f"{t['sell_date']} Sell {t['ticker']} {t['qty']:.0f} @ ${t['sell_price']:.2f} => P&L: ${t['pnl']:+,.2f}")
    print()

total = sum(t['pnl'] for t in trades)
print(f"Total Realized: ${total:+,}")