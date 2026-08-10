"""
load_db.py  —  Step 4. Put the clean data in a real database.

Optional for the analysis, but this is the file that puts "SQL" on your CV
with something behind it. SQLite ships inside Python — nothing to install,
nothing to configure, and it is a genuine relational database.

Run:  python src/load_db.py
Out:  data/retail.db
"""

import sqlite3
from pathlib import Path

import pandas as pd

DB = Path("data/retail.db")

df = pd.read_parquet("data/clean.parquet")

con = sqlite3.connect(DB)
df.to_sql("sales", con, if_exists="replace", index=False)

# indexes: without these, every per-product query scans the whole table
con.execute("CREATE INDEX IF NOT EXISTS idx_product ON sales(stock_code)")
con.execute("CREATE INDEX IF NOT EXISTS idx_date ON sales(invoice_date)")
con.commit()

print(f"Loaded {len(df):,} rows into {DB}\n")

TOP_PRODUCTS = """
SELECT description,
       SUM(quantity)            AS total_qty,
       ROUND(SUM(revenue), 2)   AS total_revenue,
       COUNT(DISTINCT invoice)  AS orders
FROM sales
GROUP BY description
ORDER BY total_qty DESC
LIMIT 10
"""

MONTHLY = """
SELECT strftime('%Y-%m', invoice_date) AS month,
       description,
       SUM(quantity)                   AS qty
FROM sales
GROUP BY month, description
ORDER BY month, qty DESC
"""

print("TOP 10 PRODUCTS BY UNITS")
print(pd.read_sql(TOP_PRODUCTS, con).to_string(index=False))

print("\nMONTHLY SERIES (first 8 rows)")
print(pd.read_sql(MONTHLY, con).head(8).to_string(index=False))

con.close()
