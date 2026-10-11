import ccxt
import pandas as pd
from datetime import datetime

def run_backtest(symbol='BTC/USDT', timeframe='1h', limit=500):
    print(f"\n[{datetime.now()] {symbol} için Backtest Başlatıldı...")
    exchange = ccxt.binance()
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    
    df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
    df['high_20'] = df['high'].rolling(window=20).max().shift(1)
    df['low_20'] = df['low'].rolling(window=20).min().shift(1)
    df['vol_ma20'] = df['volume'].rolling(window=20).mean()
    
    delta = df['close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    df['atr'] = ranges.max(axis=1).rolling(14).mean()
    
    trades = 0
    wins = 0
    
    for i in range(200, len(df)-1):
        close = df['close'].iloc[i]
        ema = df['ema200'].iloc[i]
        h20 = df['high_20'].iloc[i]
        rsi = df['rsi'].iloc[i]
        vol = df['volume'].iloc[i]
        vma = df['vol_ma20'].iloc[i]
        atr = df['atr'].iloc[i]
        
        if close > ema and close > h20 and rsi > 50 and vol > vma:
            trades += 1
            entry = close
            tp = entry + (atr * 3.0)
            sl = entry - (atr * 1.5)
            
            future_slice = df['close'].iloc[i+1:i+24] # 24 mum takip et
            hit = False
            for f_price in future_slice:
                if f_price >= tp:
                    wins += 1
                    hit = True
                    break
                elif f_price <= sl:
                    hit = True
                    break
            if not hit:
                pass

    win_rate = (wins / trades * 100) if trades > 0 else 0
    print(f"Toplam Sinyal: {trades}, Başarılı (TP): {wins}, Win-Rate: %{win_rate:.1f}")

if __name__ == "__main__":
    run_backtest('BTC/USDT')
