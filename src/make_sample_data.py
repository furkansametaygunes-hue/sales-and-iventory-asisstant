"""
make_sample_data.py
Generates a sample dataset with the SAME columns as the real
UCI "Online Retail II" file, so you can build and test the whole
pipeline today, before/without downloading the real 45 MB file.

Run:  python src/make_sample_data.py
Out:  data/raw_sample.csv
"""

import numpy as np
import pandas as pd

rng = np.random.default_rng(42)

PRODUCTS = [
    # (StockCode, Description, base monthly demand, trend per month, price)
    ("85123A", "WHITE HANGING HEART T-LIGHT HOLDER", 900, 22, 2.95),
    ("22423", "REGENCY CAKESTAND 3 TIER", 700, -14, 12.75),
    ("47566", "PARTY BUNTING", 520, 30, 4.95),
    ("84879", "ASSORTED COLOUR BIRD ORNAMENT", 610, 5, 1.69),
    ("22720", "SET OF 3 CAKE TINS PANTRY DESIGN", 480, -20, 4.95),
    ("21212", "PACK OF 72 RETRO SPOT CAKE CASES", 450, 12, 0.55),
    ("22197", "POPCORN HOLDER", 400, 40, 0.85),
    ("23084", "RABBIT NIGHT LIGHT", 380, -8, 2.08),
    ("22086", "PAPER CHAIN KIT 50'S CHRISTMAS", 300, 0, 2.55),
    ("21931", "JUMBO STORAGE BAG SUKI", 340, 9, 1.95),
    ("22384", "LUNCH BAG PINK POLKADOT", 290, 3, 1.65),
    ("20725", "LUNCH BAG RED RETROSPOT", 330, -5, 1.65),
]

COUNTRIES = ["United Kingdom"] * 12 + ["Germany", "France", "EIRE", "Spain", "Netherlands"]

months = pd.date_range("2023-01-01", "2024-12-01", freq="MS")

rows = []
invoice_no = 500000

for m_idx, month in enumerate(months):
    # December / November holiday lift, February slump
    season = {11: 1.9, 12: 1.5, 1: 0.75, 2: 0.7}.get(month.month, 1.0)

    for code, desc, base, trend, price in PRODUCTS:
        demand = max(20, (base + trend * m_idx) * season)
        n_orders = int(rng.integers(18, 40))

        for _ in range(n_orders):
            invoice_no += 1
            qty = max(1, int(rng.normal(demand / n_orders, demand / n_orders * 0.45)))
            day = int(rng.integers(1, 29))
            hour = int(rng.integers(8, 19))
            minute = int(rng.integers(0, 60))
            ts = pd.Timestamp(month.year, month.month, day, hour, minute)

            rows.append(
                {
                    "Invoice": str(invoice_no),
                    "StockCode": code,
                    "Description": desc,
                    "Quantity": qty,
                    "InvoiceDate": ts,
                    "Price": round(price * rng.uniform(0.95, 1.05), 2),
                    "Customer ID": float(rng.integers(12346, 18287)),
                    "Country": str(rng.choice(COUNTRIES)),
                }
            )

df = pd.DataFrame(rows)

# --- inject the same kind of mess the real dataset has, so the
# --- cleaning step in the guide is genuinely doing something ---

# 1. cancelled orders (Invoice starts with C, negative quantity)
cancels = df.sample(frac=0.018, random_state=1).copy()
cancels["Invoice"] = "C" + cancels["Invoice"]
cancels["Quantity"] = -cancels["Quantity"]

# 2. rows with no customer id
no_cust = df.sample(frac=0.02, random_state=2).copy()
no_cust["Customer ID"] = np.nan

# 3. rows with a missing description
no_desc = df.sample(frac=0.006, random_state=3).copy()
no_desc["Description"] = np.nan

# 4. zero-price giveaways
free = df.sample(frac=0.004, random_state=4).copy()
free["Price"] = 0.0

# 5. straight duplicates
dupes = df.sample(frac=0.008, random_state=5).copy()

df = pd.concat([df, cancels, no_cust, no_desc, free, dupes], ignore_index=True)
df = df.sample(frac=1, random_state=7).reset_index(drop=True)

df.to_csv("data/raw_sample.csv", index=False)

print(f"Wrote data/raw_sample.csv  —  {len(df):,} rows, {df['StockCode'].nunique()} products")
print(f"Date range: {df['InvoiceDate'].min().date()} → {df['InvoiceDate'].max().date()}")
