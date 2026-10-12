import os
import ccxt
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import threading
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- TELEGRAM AYARLARI ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8824923981:AAEfvNLsQRDLpR4UWijCACltFF30HIHY47Q")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "@OnyxTradeTR")

# --- KİLİT VE COOLDOWN MEKANİZMASI ---
portfolio_lock = threading.Lock()
PORTFOLIO_FILE = "paper_portfolio.json"

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

def load_portfolio():
    with portfolio_lock:
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"balance": 10000.0, "positions": [], "closed_trades": []}

def save_portfolio(portfolio):
    with portfolio_lock:
        try:
            with open(PORTFOLIO_FILE, 'w') as f:
                json.dump(portfolio, f, indent=4)
        except Exception as e:
            print(f"Portföy kaydedilemedi: {e}")

def update_and_check_positions(symbol, current_price):
    portfolio = load_portfolio()
    updated = False
    
    for pos in portfolio["positions"]:
        if pos["symbol"] == symbol and pos["status"] == "OPEN":
            entry = pos["entry"]
            sl = pos["stop_loss"]
            tp = pos["take_profit"]
            side = pos["side"]
            size = pos.get("position_size_usd", 100.0)
            
            closed = False
            result = ""
            pnl_usd = 0.0

            if side == "LONG":
                if current_price <= sl:
                    closed = True
                    result = "STOP-LOSS 🛑"
                    pnl_usd = - (size * 0.01) # %1 risk
                elif current_price >= tp:
                    closed = True
                    result = "TAKE-PROFIT 🎯"
                    pnl_usd = size * 0.03 # 1:3 R:R kârı (%3)
            elif side == "SHORT":
                if current_price >= sl:
                    closed = True
                    result = "STOP-LOSS 🛑"
                    pnl_usd = - (size * 0.01)
                elif current_price <= tp:
                    closed = True
                    result = "TAKE-PROFIT 🎯"
                    pnl_usd = size * 0.03

            if closed:
                pos["status"] = "CLOSED"
                pos["exit_price"] = current_price
                pos["result"] = result
                pos["pnl"] = pnl_usd
                pos["close_time"] = str(datetime.now())
                
                portfolio["closed_trades"].append(pos)
                portfolio["balance"] += pnl_usd
                updated = True

                emoji = "🟢" if pnl_usd > 0 else "🔴"
                msg = (
                    f"{emoji} *İŞLEM KAPANDI - {result}* {emoji}\n\n"
                    f"🏷 *Varlık:* `{symbol}`\n"
                    f"📈 *Yön:* `{side}`\n"
                    f"🎯 *Giriş Fiyatı:* `{entry:.5f}`\n"
                    f"🏁 *Kapanış Fiyatı:* `{current_price:.5f}`\n"
                    f"💰 *Net Kâr/Zarar:* `${pnl_usd:.2f}`\n"
                    f"💼 *Güncel Sanal Bakiye:* `${portfolio['balance']:.2f}`"
                )
                send_telegram_message(msg)

    if updated:
        portfolio["positions"] = [p for p in portfolio["positions"] if p["status"] == "OPEN"]
        save_portfolio(portfolio)

def open_paper_trade(symbol, side, entry, sl, tp, market_type):
    with portfolio_lock:
        portfolio = load_portfolio()
        
        for pos in portfolio["positions"]:
            if pos["symbol"] == symbol and pos["status"] == "OPEN":
                return

        recent_cutoff = datetime.now() - timedelta(hours=12)
        for pos in portfolio.get("closed_trades", []):
            if pos["symbol"] == symbol:
                close_t = datetime.strptime(pos["close_time"].split('.')[0], "%Y-%m-%d %H:%M:%S")
                if close_t > recent_cutoff:
                    return

        current_balance = portfolio["balance"]
        risk_amount = current_balance * 0.01 # Sermayenin %1'i risk
        position_size_usd = current_balance # Pozisyon büyüklüğü tabanı

        trade = {
            "id": len(portfolio["positions"]) + len(portfolio["closed_trades"]) + 1,
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "position_size_usd": position_size_usd,
            "market_type": market_type,
            "time": str(datetime.now()),
            "status": "OPEN"
        }
        
        portfolio["positions"].append(trade)
        save_portfolio(portfolio)

    emoji = "🟢" if side == "LONG" else "🔴"
    message = (
        f"{emoji} *MTF TREND + PULLBACK SİNYALİ* {emoji}\n\n"
        f"🏷 *Varlık:* `{symbol}` ({market_type})\n"
        f"📈 *Yön:* `{side}`\n"
        f"🎯 *Giriş:* `{entry:.5f}`\n"
        f"🛑 *Stop Loss:* `{sl:.5f}`\n"
        f"🎯 *Take Profit (1:3):* `{tp:.5f}`"
    )
    send_telegram_message(message)

def calculate_indicators(df):
    if df is None or len(df) < 200:
        return None
    
    close = df['close']
    high = df['high']
    low = df['low']

    df['ema50'] = close.ewm(span=50, adjust=False).mean()
    df['ema200'] = close.ewm(span=200, adjust=False).mean()

    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(14).mean()

    return df

def process_multi_timeframe(df_1h, df_4h, symbol, market_type):
    try:
        df_1h = calculate_indicators(df_1h)
        df_4h = calculate_indicators(df_4h)
        
        if df_1h is None or df_4h is None:
            return

        current_close = df_1h['close'].iloc[-2]
        update_and_check_positions(symbol, current_close)

        # 4H Trend Filtresi
        ema50_4h = df_4h['ema50'].iloc[-2]
        ema200_4h = df_4h['ema200'].iloc[-2]
        close_4h = df_4h['close'].iloc[-2]

        is_4h_uptrend = (close_4h > ema50_4h) and (ema50_4h > ema200_4h)
        is_4h_downtrend = (close_4h < ema50_4h) and (ema50_4h < ema200_4h)

        # 1H Destek/Direnç ve Onay (Pullback + RSI Doğrulaması)
        ema50_1h = df_1h['ema50'].iloc[-2]
        low_1h = df_1h['low'].iloc[-2]
        high_1h = df_1h['high'].iloc[-2]
        rsi_1h = df_1h['rsi'].iloc[-2]
        atr_1h = df_1h['atr'].iloc[-2]

        # --- LONG STRATEJİSİ ---
        is_long_pullback = is_4h_uptrend and (low_1h <= ema50_1h * 1.005) and (current_close > ema50_1h) and (rsi_1h > 50)
        if is_long_pullback:
            entry = current_close
            sl = entry - (atr_1h * 1.5)
            tp = entry + ((entry - sl) * 3.0) # Kesin 1:3 R:R
            open_paper_trade(symbol, "LONG", entry, sl, tp, market_type)
            return

        # --- SHORT STRATEJİSİ ---
        is_short_pullback = is_4h_downtrend and (high_1h >= ema50_1h * 0.995) and (current_close < ema50_1h) and (rsi_1h < 50)
        if is_short_pullback:
            entry = current_close
            sl = entry + (atr_1h * 1.5)
            tp = entry - ((sl - entry) * 3.0) # Kesin 1:3 R:R
            open_paper_trade(symbol, "SHORT", entry, sl, tp, market_type)

    except Exception:
        pass

def analyze_crypto_spot_mtf(symbol):
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        ohlcv_1h = exchange.fetch_ohlcv(symbol, '1h', limit=250)
        ohlcv_4h = exchange.fetch_ohlcv(symbol, '4h', limit=250)
        df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        process_multi_timeframe(df_1h, df_4h, symbol, "KRİPTO SPOT")
    except Exception:
        pass

def analyze_crypto_future_mtf(symbol):
    try:
        exchange = ccxt.binance({'options': {'defaultType': 'future'}, 'enableRateLimit': True})
        ohlcv_1h = exchange.fetch_ohlcv(symbol, '1h', limit=250)
        ohlcv_4h = exchange.fetch_ohlcv(symbol, '4h', limit=250)
        df_1h = pd.DataFrame(ohlcv_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df_4h = pd.DataFrame(ohlcv_4h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        process_multi_timeframe(df_1h, df_4h, symbol, "KRİPTO VADELİ")
    except Exception:
        pass

def analyze_yahoo_batch_mtf(symbols, market_type):
    try:
        data = yf.download(symbols, interval='1h', period='60d', group_by='ticker', progress=False, threads=True)
        for symbol in symbols:
            try:
                if len(symbols) == 1:
                    df_1h = data.copy()
                else:
                    df_1h = data[symbol].copy()
                
                if df_1h is not None and not df_1h.empty:
                    df_1h = df_1h.dropna()
                    df_1h = df_1h.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
                    df_4h = df_1h.resample('4h').agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
                    process_multi_timeframe(df_1h, df_4h, symbol, market_type)
            except:
                continue
    except Exception:
        pass

def send_performance_summary():
    portfolio = load_portfolio()
    closed = portfolio.get("closed_trades", [])
    if not closed:
        return
        
    total_trades = len(closed)
    wins = len([t for t in closed if t["pnl"] > 0])
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    total_pnl = sum([t["pnl"] for t in closed])

    msg = (
        f"📊 *PERFORMANS ÖZETİ* 📊\n\n"
        f"📈 *Toplam İşlem:* `{total_trades}`\n"
        f"🏆 *Başarı Oranı:* `%{win_rate:.1f}`\n"
        f"💵 *Net PnL:* `${total_pnl:.2f}`\n"
        f"💼 *Sanal Bakiye:* `${portfolio['balance']:.2f}`"
    )
    send_telegram_message(msg)

def run_scanner():
    print(f"\n[{datetime.now()}] MTF Trend + Pullback Taraması Başlatıldı...")

    try:
        ex_spot = ccxt.binance()
        spot_markets = ex_spot.load_markets()
        spot_list = [s for s in spot_markets if '/USDT' in s and ':' not in s]
    except:
        spot_list = []

    try:
        ex_fut = ccxt.binance({'options': {'defaultType': 'future'}})
        fut_markets = ex_fut.load_markets()
        fut_list = [s for s in fut_markets if '/USDT' in s and ':' not in s]
    except:
        fut_list = []

    forex_commodities = ['EURUSD=X', 'GBPUSD=X', 'USDJPY=X', 'GC=F', 'CL=F']
    bist_list = [f"{s}.IS" for s in ['THYAO', 'GARAN', 'AKBNK', 'EREGL', 'KCHOL', 'ASELS']]
    us_stocks = ['AAPL', 'MSFT', 'NVDA', 'TSLA']
    all_stocks = forex_commodities + bist_list + us_stocks

    with ThreadPoolExecutor(max_workers=30) as executor:
        futures = [executor.submit(analyze_crypto_spot_mtf, sym) for sym in spot_list]
        futures += [executor.submit(analyze_crypto_future_mtf, sym) for sym in fut_list]
        
        chunk_size = 20
        for i in range(0, len(all_stocks), chunk_size):
            chunk = all_stocks[i:i + chunk_size]
            futures.append(executor.submit(analyze_yahoo_batch_mtf, chunk, "KÜRESEL PİYASA"))

        for future in as_completed(futures):
            pass

    send_performance_summary()
    print("Tarama tamamlandı.")

if __name__ == "__main__":
    run_scanner()
