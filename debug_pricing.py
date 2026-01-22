import yfinance as yf
import requests
from datetime import date, timedelta
import pandas as pd

start_date = date(2025, 12, 1) # Check a recent range relevant to current 2026 date
today = date(2026, 1, 16)

print("--- TESTING BRENT (Yahoo) ---")
try:
    brent_df = yf.download("BZ=F", start=start_date, end=today, progress=False)
    print("Brent DataFrame shape:", brent_df.shape)
    print("Brent Columns:", brent_df.columns)
    if not brent_df.empty:
        print("First row:", brent_df.iloc[0])
        # Simulation of code logic
        current_ts = brent_df.index[0]
        r_brent = brent_df.loc[brent_df.index.normalize() == current_ts.normalize()]
        print("Sample lookup result:", r_brent)
        if hasattr(r_brent, 'columns') and isinstance(r_brent.columns, pd.MultiIndex):
            print("Detected MultiIndex columns")
except Exception as e:
    print("Brent Error:", e)

print("\n--- TESTING TRM (Gov.co) ---")
try:
    url_trm = "https://www.datos.gov.co/resource/32sa-8pi3.json?$where=vigenciadesde >= '2025-12-01T00:00:00.000'"
    resp = requests.get(url_trm, timeout=10)
    data = resp.json()
    print("Records found:", len(data))
    if data:
        print("First record:", data[0])
    else:
        print("No records for criteria. checking without criteria (limit 1)...")
        resp2 = requests.get("https://www.datos.gov.co/resource/32sa-8pi3.json?$limit=1", timeout=10)
        print("Sample:", resp2.json())
except Exception as e:
    print("TRM Error:", e)
