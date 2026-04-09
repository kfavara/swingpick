from dotenv import load_dotenv
load_dotenv()
from app import fetch_alpaca_history

history = fetch_alpaca_history('2026-03-19')
print(f'Fetched {len(history)} trades\n')
for h in history:
    print(f"{h.get('buy_date')} {h['ticker']}: Buy ${h['buy_price']} -> Sell ${h['sell_price']} Qty:{h['qty']} P&L:${h['pnl_dollars']:+,.2f}")

total = sum(h['pnl_dollars'] for h in history)
print(f"\nTotal: ${total:+,.2f}")