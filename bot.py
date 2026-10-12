import os
import ccxt
import yfinance as yf
import pandas as pd
import numpy as np
import requests
import json
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- TELEGRAM AYARLARI ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8824923981:AAEfvNLsQRDLpR4UWijCACltFF30HIHY47Q")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "@OnyxTradeTR")

# --- KİLİT MEKANİZMASI ---
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
            
            closed = False
            result = ""
            pnl = 0.0

            if side == "LONG":
                if current_price <= sl:
                    closed = True
                    result = "STOP-LOSS"
                    pnl = sl - entry
                elif current_price >= tp:
                    closed = True
                    result = "TAKE-PROFIT"
                    pnl = tp - entry
            elif side == "SHORT":
                if current_price >= sl:
                    closed = True
                    result = "STOP-LOSS"
                    pnl = entry - sl
                elif current_price <= tp:
                    closed = True
                    result = "TAKE-PROFIT"
                    pnl = entry - tp

            if closed:
                pos["status"] = "CLOSED"
                pos["exit_price"] = current_price
                pos["result"] = result
                pos["pnl"] = pnl
                pos["close_time"] = str(datetime.now())
                
                portfolio["closed_trades"].append(pos)
                portfolio["balance"] += pnl * 100
                updated = True

                emoji = "🟢" if pnl > 0 else "🔴"
                msg = (
                    f"{emoji} *İŞLEM KAPANDI ({result})* {emoji}\n\n"
                    f"🏷 *Varlık:* `{symbol}`\n"
                    f"📈 *Yön:* `{side}`\n"
                    f"🎯 *Giriş:* `{entry:.5f}`\n"
                    f"🏁 *Çıkış:* `{current_price:.5f}`\n"
                    f"💰 *Kâr/Zarar:* `{pnl:.5f}`\n"
                    f"💼 *Güncel Bakiye:* `${portfolio['balance']:.2f}`"
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

        trade = {
            "id": len(portfolio["positions"]) + len(portfolio["closed_trades"]) + 1,
            "symbol": symbol,
            "side": side,
            "entry": entry,
            "stop_loss": sl,
            "take_profit": tp,
            "market_type": market_type,
            "time": str(datetime.now()),
            "status": "OPEN"
        }
        
        portfolio["positions"].append(trade)
        save_portfolio(portfolio)

    emoji = "🟢" if side == "LONG" else "🔴"
    message = (
        f"{emoji} *ÇOKLU İNDİKATÖR TEYİTLİ SİNYAL* {emoji}\n\n"
        f"🏷 *Varlık:* `{symbol}` ({market_type})\n"
        f"📈 *Yön:* `{side}`\n"
        f"🎯 *Giriş:* `{entry:.5f}`\n"
        f"🛑 *Stop Loss:* `{sl:.5f}`\n"
        f"🎯 *Take Profit:* `{tp:.5f}`"
    )
    send_telegram_message(message)

# --- İNDİKATÖR HESAPLAMA MOTORU ---
def calculate_advanced_indicators(df):
    if df is None or len(df) < 100:
        return None
    
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']

    # 1. Hull Moving Average (HullMA)
    half_length = int(9 / 2)
    sqrt_length = int(np.sqrt(9))
    wma_half = close.rolling(half_length).apply(lambda x: np.dot(x, np.arange(1, len(x)+1)) / np.arange(1, len(x)+1).sum(), raw=True)
    wma_full = close.rolling(9).apply(lambda x: np.dot(x, np.arange(1, len(x)+1)) / np.arange(1, len(x)+1).sum(), raw=True)
    df['hull_ma'] = (2 * wma_half - wma_full).rolling(sqrt_length).apply(lambda x: np.dot(x, np.arange(1, len(x)+1)) / np.arange(1, len(x)+1).sum(), raw=True)

    # 2. Supertrend
    atr_period = 10
    multiplier = 3.0
    hl2 = (high + low) / 2
    
    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(atr_period).mean()
    df['atr'] = atr

    upper_basic = hl2 + (multiplier * atr)
    lower_basic = hl2 - (multiplier * atr)
    
    supertrend = [True] * len(df)
    for i in range(1, len(df)):
        if close.iloc[i] > upper_basic.iloc[i-1]:
            supertrend[i] = True
        elif close.iloc[i] < lower_basic.iloc[i-1]:
            supertrend[i] = False
        else:
            supertrend[i] = supertrend[i-1]
    df['supertrend'] = supertrend

    # 3. N MACD
    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    df['n_macd'] = ema_fast - ema_slow
    df['n_macd_signal'] = df['n_macd'].ewm(span=9, adjust=False).mean()

    # 4. WaveTrend (WT_CROSS_LB)
    ap = (high + low + close) / 3
    esa = ap.ewm(span=10, adjust=False).mean()
    d = (ap - esa).abs().ewm(span=10, adjust=False).mean()
    ci = (ap - esa) / (0.015 * d)
    df['wt1'] = ci.ewm(span=21, adjust=False).mean()
    df['wt2'] = df['wt1'].rolling(4).mean()

    # 5. TrendSpeed Analyzer (Fiyat Değişim Hızı)
    df['trend_speed'] = close.diff(5)

    # 6. RSI (14)
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # 7. CCI (20)
    tp = (high + low + close) / 3
    sma_tp = tp.rolling(20).mean()
    mad = tp.rolling(20).apply(lambda x: np.abs(x - x.mean()).mean(), raw=True)
    df['cci'] = (tp - sma_tp) / (0.015 * mad)

    return df

def process_signals(df_1h, symbol, market_type):
    try:
        df = calculate_advanced_indicators(df_1h)
        if df is None:
            return

        current_close = df['close'].iloc[-2]
        update_and_check_positions(symbol, current_close)

        # Değerler
        st = df['supertrend'].iloc[-2]
        hull = df['hull_ma'].iloc[-2]
        hull_prev = df['hull_ma'].iloc[-3]
        
        macd = df['n_macd'].iloc[-2]
        macd_sig = df['n_macd_signal'].iloc[-2]
        
        wt1 = df['wt1'].iloc[-2]
        wt2 = df['wt2'].iloc[-2]
        wt1_prev = df['wt1'].iloc[-3]
        wt2_prev = df['wt2'].iloc[-3]
        
        t_speed = df['trend_speed'].iloc[-2]
        rsi = df['rsi'].iloc[-2]
        cci = df['cci'].iloc[-2]
        atr = df['atr'].iloc[-2]

        # --- LONG TEYİT KURALLARI ---
        is_st_bullish = st == True
        is_hull_bullish = hull > hull_prev
        is_macd_bullish = macd > macd_sig
        is_wt_bullish = (wt1 > wt2) and (wt1_prev <= wt2_prev)  # WT Cross LB yukarı kesişim
        is_speed_bullish = t_speed > 0
        is_rsi_bullish = rsi > 50
        is_cci_bullish = cci > 0

        if is_st_bullish and is_hull_bullish and is_macd_bullish and is_wt_bullish and is_speed_bullish and is_rsi_bullish and is_cci_bullish:
            entry = current_close
            sl = entry - (atr * 1.5)
            tp = entry + (atr * 3.0)
            open_paper_trade(symbol, "LONG", entry, sl, tp, market_type)
            return

        # --- SHORT TEYİT KURALLARI ---
        is_st_bearish = st == False
        is_hull_bearish = hull < hull_prev
        is_macd_bearish = macd < macd_sig
        is_wt_bearish = (wt1 < wt2) and (wt1_prev >= wt2_prev)  # WT Cross LB aşağı kesişim
        is_speed_bearish = t_speed < 0
        is_rsi_bearish = rsi < 50
        is_cci_bearish = cci < 0

        if is_st_bearish and is_hull_bearish and is_macd_bearish and is_wt_bearish and is_speed_bearish and is_rsi_bearish and is_cci_bearish:
            entry = current_close
            sl = entry + (atr * 1.5)
            tp = entry - (atr * 3.0)
            open_paper_trade(symbol, "SHORT", entry, sl, tp, market_type)

    except Exception:
        pass

def analyze_crypto_spot(symbol):
    try:
        exchange = ccxt.binance({'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=150)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        process_signals(df, symbol, "KRİPTO SPOT")
    except Exception:
        pass

def analyze_crypto_future(symbol):
    try:
        exchange = ccxt.binance({'options': {'defaultType': 'future'}, 'enableRateLimit': True})
        ohlcv = exchange.fetch_ohlcv(symbol, '1h', limit=150)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        process_signals(df, symbol, "KRİPTO VADELİ")
    except Exception:
        pass

def analyze_yahoo_batch(symbols, market_type):
    try:
        data = yf.download(symbols, interval='1h', period='30d', group_by='ticker', progress=False, threads=True)
        for symbol in symbols:
            try:
                if len(symbols) == 1:
                    df = data.copy()
                else:
                    df = data[symbol].copy()
                
                if df is not None and not df.empty:
                    df = df.dropna()
                    df = df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
                    process_signals(df, symbol, market_type)
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
        f"💵 *Net PnL:* `{total_pnl:.5f}`\n"
        f"💼 *Sanal Bakiye:* `${portfolio['balance']:.2f}`"
    )
    send_telegram_message(msg)

def run_scanner():
    print(f"\n[{datetime.now()}] Çoklu İndikatör Teyitli Tarama Başlatıldı...")

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
        futures = [executor.submit(analyze_crypto_spot, sym) for sym in spot_list]
        futures += [executor.submit(analyze_crypto_future, sym) for sym in fut_list]
        
        chunk_size = 20
        for i in range(0, len(all_stocks), chunk_size):
            chunk = all_stocks[i:i + chunk_size]
            futures.append(executor.submit(analyze_yahoo_batch, chunk, "KÜRESEL PİYASA"))

        for future in as_completed(futures):
            pass

    send_performance_summary()
    print("Tarama tamamlandı.")

if __name__ == "__main__":
    run_scanner()
