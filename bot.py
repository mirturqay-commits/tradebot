import os
import ccxt
import yfinance as yf
import pandas as pd
import requests
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- GÜVENLİĞE ALINMIŞ TELEGRAM AYARLARI ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

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
        if df is None or len(df) < 60:
            return
            
        df['ema50'] = df['close'].ewm(span=50, adjust=False).mean()
        
        left_bars = 5
        right_bars = 5
        
        last_pivot_high = None
        for i in range(len(df) - right_bars - 2, left_bars, -1):
            is_high = True
            current_high = df['high'].iloc[i]
            for j in range(1, left_bars + 1):
                if df['high'].iloc[i - j] >= current_high:
                    is_high = False
            for j in range(1, right_bars + 1):
                if df['high'].iloc[i + j] >= current_high:
                    is_high = False
            if is_high:
                last_pivot_high = current_high
                break
        
        if last_pivot_high is None:
            return

        current_close = df['close'].iloc[-2]
        current_high = df['high'].iloc[-2]
        current_open = df['open'].iloc[-2]
        current_ema50 = df['ema50'].iloc[-2]
        
        is_near_resistance = (last_pivot_high * 0.998) <= current_high <= (last_pivot_high * 1.005)
        is_below_ema = current_close < current_ema50
        is_bearish = current_close < current_open
        
        if is_near_resistance and is_below_ema and is_bearish:
            entry_price = current_close
            stop_loss = last_pivot_high * 1.002
            risk = stop_loss - entry_price
            take_profit = entry_price - (risk * 2.0)
            
            message = (
                f"🚨 *PROFESYONEL SHORT SİNYALİ ({market_type})* 🚨\n\n"
                f"🏷 *Varlık:* `{symbol}`\n"
                f"📉 *Giriş Fiyatı:* `{entry_price:.5f}`\n"
                f"🛑 *Stop Loss:* `{stop_loss:.5f}`\n"
                f"🎯 *Take Profit:* `{take_profit:.5f}`\n"
                f"📊 *Direnç Seviyesi:* `{last_pivot_high:.5f}`"
            )
            
            send_telegram_message(message)
            print(f"Sinyal gönderildi: {symbol}")
            
    except Exception as e:
        pass

def analyze_crypto(symbol):
    try:
        exchange = ccxt.binance({'options': {'defaultType': 'future'}, 'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        check_and_send(df, symbol, "KRİPTO")
    except Exception:
        pass

def analyze_yahoo(symbol, market_type):
    try:
        df = yf.download(symbol, interval='1h', period='5d', progress=False)
        if not df.empty:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            df = df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
            check_and_send(df, symbol, market_type)
    except Exception:
        pass

def run_scanner():
    print(f"\n[{datetime.now()}] Profesyonel tarama başlatıldı...")

    try:
        ex = ccxt.binance({'options': {'defaultType': 'future'}})
        markets = ex.load_markets()
        crypto_list = [s for s in markets if '/USDT' in s and ':' not in s][:300]
    except:
        crypto_list = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT']

    forex_list = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'AUDUSD=X', 'GC=F', 'CL=F']
    stock_list = ['THYAO.IS', 'GARAN.IS', 'AKBNK.IS', 'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA']

    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(analyze_crypto, sym) for sym in crypto_list]
        futures += [executor.submit(analyze_yahoo, sym, "FOREX/EMTİA") for sym in forex_list]
        futures += [executor.submit(analyze_yahoo, sym, "HİSSE SENEDİ") for sym in stock_list]

        for future in as_completed(futures):
            pass

    print("Tarama tamamlandı.")

if __name__ == "__main__":
    run_scanner()
