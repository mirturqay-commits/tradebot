import streamlit as st
import json
import os
import pandas as pd

st.set_page_config(page_title="Pro Donchian Trading Dashboard", layout="wide")

st.title("🚀 Pro Donchian Scanner & Paper Trading Dashboard")

PORTFOLIO_FILE = "paper_portfolio.json"

if os.path.exists(PORTFOLIO_FILE):
    with open(PORTFOLIO_FILE, 'r') as f:
        data = json.load(f)
else:
    data = {"balance": 10000.0, "positions": [], "closed_trades": []}

col1, col2, col3 = st.columns(3)
col1.metric("💼 Sanal Bakiye", f"${data.get('balance', 10000.0):,.2f}")
col2.metric("📈 Açık Pozisyon Sayısı", len(data.get("positions", [])))
col3.metric("🏁 Kapatılan İşlem Sayısı", len(data.get("closed_trades", [])))

st.divider()

st.subheader("🟢 Açık Pozisyonlar")
positions = data.get("positions", [])
if positions:
    st.dataframe(pd.DataFrame(positions))
else:
    st.info("Şu an açık sanal pozisyon bulunmuyor.")

st.subheader("📊 Geçmiş İşlem Günlüğü & Performans")
closed = data.get("closed_trades", [])
if closed:
    st.dataframe(pd.DataFrame(closed))
else:
    st.info("Henüz kapanmış işlem yok.")
