import sys
sys.path.insert(0, '.')
from app import fetch_alpaca_history

history = fetch_alpaca_history('2026-03-19')
print(f"Fetched {len(history)} trades")
for h in history:
    print(f"{h['ticker']}: Buy ${h['buy_price']} -> Sell ${h['sell_price']} | P&L: ${h['pnl_dollars']:+.2f}")
if history:
    print(f"\nTotal: ${sum(h['pnl_dollars'] for h in history):+,.2f}")