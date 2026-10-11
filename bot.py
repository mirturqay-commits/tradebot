import ccxt
import yfinance as yf
import pandas as pd
import requests
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- TELEGRAM AYARLARI ---
TELEGRAM_BOT_TOKEN = "8824923981:AAEfvNLsQRDLpR4UWijCACltFF30HIHY47Q"
TELEGRAM_CHAT_ID = "@OnyxTradeTR"

def send_telegram_message(message):
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

# Ortak Teknik Analiz Mantığı
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
                f"🚨 *SHORT SİNYALİ ({market_type})* 🚨\n\n"
                f"🏷 *Varlık:* `{symbol}`\n"
                f"📉 *Giriş Fiyatı:* `{entry_price:.5f}`\n"
                f"🛑 *Stop Loss:* `{stop_loss:.5f}`\n"
                f"🎯 *Take Profit:* `{take_profit:.5f}`\n"
                f"📊 *Direnç Seviyesi:* `{last_pivot_high:.5f}`"
            )
            
            send_telegram_message(message)
            print(f"Sinyal gönderildi: {symbol}")
            
    except Exception as e:
        pass # Hataları bastırıp taramanın kesilmesini önlüyoruz

# Tekil Kripto Analizi (Binance)
def analyze_crypto(symbol):
    try:
        exchange = ccxt.binance({'options': {'defaultType': 'future'}, 'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=100)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        check_and_send(df, symbol, "KRİPTO")
    except Exception:
        pass

# Tekil Hisse/Forex Analizi (Yahoo Finance)
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
    print(f"\n[{datetime.now()}] 1000+ Varlık paralel olarak taranıyor...")

    # 1. Otomatik olarak Binance'teki en popüler vadeli işlem paritelerini çekme (Örn: İlk 250-300 coin)
    try:
        ex = ccxt.binance({'options': {'defaultType': 'future'}})
        markets = ex.load_markets()
        crypto_list = [s for s in markets if '/USDT' in s and ':' not in s][:300] # Hacimli ilk 300 coin
    except:
        crypto_list = ['BTC/USDT', 'ETH/USDT', 'SOL/USDT', 'AVAX/USDT']

    # 2. Popüler Forex ve Emtialar
    forex_list = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'AUDUSD=X', 'USDCAD=X', 'NZDUSD=X', 'GC=F', 'SI=F', 'CL=F', 'BZ=F']

    # 3. BIST ve Global Hisse Senetleri Havuzu (Örnek geniş liste)
    # Buraya dilediğin kadar BIST ve Amerikan hissesi ekleyebilirsin
    stock_list = [
        'THYAO.IS', 'GARAN.IS', 'AKBNK.IS', 'EREGL.IS', 'KCHOL.IS', 'SAHOL.IS', 'ASELS.IS', 'TUPRS.IS', 'BIMAS.IS', 'YKBNK.IS',
        'AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'NFLX', 'AMD', 'INTC'
        # Listeyi dilediğin kadar binlerce hisse sembolüyle büyütebilirsin
    ]

    # Paralel Çalıştırma (ThreadPoolExecutor ile aynı anda çoklu sorgu)
    with ThreadPoolExecutor(max_workers=20) as executor:
        # Kriptoları kuyruğa ekle
        futures = [executor.submit(analyze_crypto, sym) for sym in crypto_list]
        # Forexleri kuyruğa ekle
        futures += [executor.submit(analyze_yahoo, sym, "FOREX/EMTİA") for sym in forex_list]
        # Hisseleri kuyruğa ekle
        futures += [executor.submit(analyze_yahoo, sym, "HİSSE SENEDİ") for sym in stock_list]

        # Tüm işlemlerin bitmesini bekle
        for future in as_completed(futures):
            pass

    print("Tarama tamamlandı. Sonraki tarama için 15 dakika bekleniyor...")

if __name__ == "__main__":
    while True:
        run_scanner()
        time.sleep(900)
