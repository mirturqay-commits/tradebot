import os
import ccxt
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- TELEGRAM AYARLARI ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8824923981:AAEfvNLsQRDLpR4UWijCACltFF30HIHY47Q")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "@OnyxTradeTR")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram kimlik bilgileri eksik!")
        return
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }
    try:
        requests.post(url, json=payload, timeout=5)
    except Exception as e:
        print(f"Telegram mesajı gönderilemedi: {e}")

def check_and_send(df, symbol, market_type):
    try:
        if df is None or len(df) < 200:
            return
            
        # 1. Trend Filtresi (200 EMA)
        df['ema200'] = df['close'].ewm(span=200, adjust=False).mean()
        
        # 2. Donchian Kanalı (20 Dönem Kırılımı)
        df['high_20'] = df['high'].rolling(window=20).max().shift(1)
        df['low_20'] = df['low'].rolling(window=20).min().shift(1)
        
        # 3. Hacim Onay Filtresi (20 Dönem Hacim Ortalaması)
        df['vol_ma20'] = df['volume'].rolling(window=20).mean()
        
        # 4. RSI Momentum Filtresi (14 Dönem)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 5. ATR (Volatilite ve Risk Hesaplama)
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        df['atr'] = ranges.max(axis=1).rolling(14).mean()

        current_close = df['close'].iloc[-2]
        current_ema200 = df['ema200'].iloc[-2]
        high_20 = df['high_20'].iloc[-2]
        low_20 = df['low_20'].iloc[-2]
        current_atr = df['atr'].iloc[-2]
        current_vol = df['volume'].iloc[-2]
        vol_ma20 = df['vol_ma20'].iloc[-2]
        current_rsi = df['rsi'].iloc[-2]
        
        is_volume_confirmed = current_vol > vol_ma20
        
        # --- LONG SİNYALİ ---
        if current_close > current_ema200 and current_close > high_20 and is_volume_confirmed and current_rsi > 50:
            entry_price = current_close
            stop_loss = entry_price - (current_atr * 2.0)
            take_profit = entry_price + (current_atr * 4.0)
            
            message = (
                f"🟢 *PRO DONCHIAN LONG ({market_type})* 🟢\n\n"
                f"🏷 *Varlık:* `{symbol}`\n"
                f"📈 *Giriş:* `{entry_price:.5f}`\n"
                f"🛑 *Stop:* `{stop_loss:.5f}`\n"
                f"🎯 *Hedef:* `{take_profit:.5f}`\n"
                f"📊 *RSI:* `{current_rsi:.1f}` | *Hacim:* `Onaylı`"
            )
            send_telegram_message(message)
            return

        # --- SHORT SİNYALİ ---
        if current_close < current_ema200 and current_close < low_20 and is_volume_confirmed and current_rsi < 50:
            entry_price = current_close
            stop_loss = entry_price + (current_atr * 2.0)
            take_profit = entry_price - (current_atr * 4.0)
            
            message = (
                f"🔴 *PRO DONCHIAN SHORT ({market_type})* 🔴\n\n"
                f"🏷 *Varlık:* `{symbol}`\n"
                f"📉 *Giriş:* `{entry_price:.5f}`\n"
                f"🛑 *Stop:* `{stop_loss:.5f}`\n"
                f"🎯 *Hedef:* `{take_profit:.5f}`\n"
                f"📊 *RSI:* `{current_rsi:.1f}` | *Hacim:* `Onaylı`"
            )
            send_telegram_message(message)
            
    except Exception as e:
        pass

def analyze_crypto_spot(symbol):
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=250)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        check_and_send(df, symbol, "KRİPTO SPOT")
    except Exception:
        pass

def analyze_crypto_future(symbol):
    try:
        exchange = ccxt.binance({'options': {'defaultType': 'future'}, 'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=250)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        check_and_send(df, symbol, "KRİPTO VADELİ")
    except Exception:
        pass

def analyze_yahoo_batch(symbols, market_type):
    try:
        data = yf.download(symbols, interval='1h', period='15d', group_by='ticker', progress=False, threads=True)
        for symbol in symbols:
            try:
                if len(symbols) == 1:
                    df = data.copy()
                else:
                    df = data[symbol].copy()
                
                if df is not None and not df.empty:
                    df = df.dropna()
                    df = df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
                    check_and_send(df, symbol, market_type)
            except:
                continue
    except Exception:
        pass

def run_scanner():
    print(f"\n[{datetime.now()}] 5000+ Varlık Dev Tarama (Donchian + EMA200 + Hacim + RSI + ATR) Başlatıldı...")

    # 1. Binance Spot Piyasası
    try:
        ex_spot = ccxt.binance()
        spot_markets = ex_spot.load_markets()
        spot_list = [s for s in spot_markets if '/USDT' in s and ':' not in s]
    except:
        spot_list = []

    # 2. Binance Vadeli Piyasası
    try:
        ex_fut = ccxt.binance({'options': {'defaultType': 'future'}})
        fut_markets = ex_fut.load_markets()
        fut_list = [s for s in fut_markets if '/USDT' in s and ':' not in s]
    except:
        fut_list = []

    # 3. Küresel Piyasa (Forex, Emtia, BIST ve ABD Hisseleri)
    forex_commodities = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'AUDUSD=X', 'USDCAD=X', 'NZDUSD=X', 'GC=F', 'SI=F', 'CL=F', 'NG=F', 'BZ=F']
    bist_list = [f"{s}.IS" for s in ['THYAO', 'GARAN', 'AKBNK', 'EREGL', 'KCHOL', 'SAHOL', 'ASELS', 'BIMAS', 'TUPRS', 'YKBNK', 'ISCTR', 'KRDMD', 'PETKM', 'SASA', 'HEKTS']]
    us_stocks = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'NFLX', 'AMD', 'INTC', 'JPM', 'V', 'MA', 'DIS', 'PYPL']

    all_stocks = forex_commodities + bist_list + us_stocks

    print(f"Toplam Taranacak Kripto (Spot + Vadeli): {len(spot_list) + len(fut_list)}")
    print(f"Toplam Taranacak Hisse/Emtia/Forex: {len(all_stocks)}")

    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(analyze_crypto_spot, sym) for sym in spot_list]
        futures += [executor.submit(analyze_crypto_future, sym) for sym in fut_list]
        
        chunk_size = 20
        for i in range(0, len(all_stocks), chunk_size):
            chunk = all_stocks[i:i + chunk_size]
            futures.append(executor.submit(analyze_yahoo_batch, chunk, "KÜRESEL PİYASA"))

        for future in as_completed(futures):
            pass

    print("Dev tarama tamamlandı.")

if __name__ == "__main__":
    run_scanner()
