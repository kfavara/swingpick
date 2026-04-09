import yfinance as yf

tickers = ['AKAM', 'APA', 'CTRA', 'OXY', 'VRSN']
for t in tickers:
    try:
        stock = yf.Ticker(t)
        df = stock.history(period='5d')
        if df.empty:
            print(f'{t}: NO DATA')
        else:
            price = df['Close'].iloc[-1]
            print(f'{t}: OK - ${price:.2f}')
    except Exception as e:
        print(f'{t}: ERROR - {e}')