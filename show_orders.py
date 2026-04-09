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

while True:
    url = 'https://paper-api.alpaca.markets/v2/orders?status=filled&limit=100'
    if page_token:
        url += f'&after={page_token}'
    
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"Error: {r.status_code} {r.text}")
        break
    orders = r.json()
    if not orders:
        break
    
    for o in orders:
        all_orders.append({
            'symbol': o['symbol'],
            'side': o['side'],
            'qty': o['qty'],
            'price': o['filled_avg_price'],
            'date': o['filled_at'][:10]
        })
    
    if len(orders) < 100:
        break
    page_token = orders[-1].get('id')

print("=== ALL FILLED ORDERS ===\n")
for o in all_orders:
    print(f"{o['date']} {o['side'].upper()} {o['qty']} {o['symbol']} @ ${o['price']}")