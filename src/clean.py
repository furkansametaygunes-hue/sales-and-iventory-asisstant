"""
clean.py  —  Step 2 of the pipeline.

Takes the raw file and produces a clean, analysis-ready table.
Every rule below is a business decision, not just a technical one —
write the reason down, because that is what the university portfolio
is actually being judged on.

Run:  python src/clean.py
In:   data/raw_sample.csv     (or data/online_retail_II.csv)
Out:  data/clean.parquet
"""

import sys
from pathlib import Path

import pandas as pd

RAW = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/raw_sample.csv")
OUT = Path("data/clean.parquet")


def load(path: Path) -> pd.DataFrame:
    if path.suffix == ".xlsx":
        # the real UCI file is Excel with 2 sheets — read and stack both
        sheets = pd.read_excel(path, sheet_name=None)
        return pd.concat(sheets.values(), ignore_index=True)
    return pd.read_csv(path)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    report = {"start": len(df)}

    # normalise column names (the real file has "Customer ID" with a space)
    df = df.rename(
        columns={
            "Customer ID": "customer_id",
            "InvoiceDate": "invoice_date",
            "StockCode": "stock_code",
            "Description": "description",
            "Quantity": "quantity",
            "Price": "price",
            "Invoice": "invoice",
            "Country": "country",
        }
    )

    df["invoice_date"] = pd.to_datetime(df["invoice_date"])
    df["invoice"] = df["invoice"].astype(str)
    df["stock_code"] = df["stock_code"].astype(str).str.strip().str.upper()
    df["description"] = df["description"].astype(str).str.strip().str.upper()

    # 1. drop exact duplicate rows — same invoice, product, time, qty
    df = df.drop_duplicates()
    report["after_dupes"] = len(df)

    # 2. remove cancellations (invoice prefixed with C) and their
    #    negative quantities. WHY: a cancelled order was never "used",
    #    so counting it would inflate demand.
    df = df[~df["invoice"].str.startswith("C")]
    df = df[df["quantity"] > 0]
    report["after_cancels"] = len(df)

    # 3. drop zero/negative price rows — samples, giveaways, data errors.
    #    WHY: they distort revenue, and we want commercial demand.
    df = df[df["price"] > 0]
    report["after_price"] = len(df)

    # 4. drop rows with no product description (unidentifiable product)
    df = df[df["description"].notna() & (df["description"] != "NAN")]
    report["after_desc"] = len(df)

    # 5. remove non-product stock codes (postage, fees, manual adjustments)
    #    WHY: "POST" is not a product; it would rank as a top seller.
    junk = {"POST", "D", "DOT", "M", "S", "AMAZONFEE", "BANK CHARGES", "CRUK", "C2"}
    df = df[~df["stock_code"].isin(junk)]
    report["after_junk"] = len(df)

    # 6. trim extreme outliers — keep the 99.9th percentile.
    #    WHY: one 80,000-unit bulk order can invent a fake trend.
    cap = df["quantity"].quantile(0.999)
    df = df[df["quantity"] <= cap]
    report["after_outliers"] = len(df)

    # 7. derived fields used everywhere downstream
    df["revenue"] = df["quantity"] * df["price"]
    df["month"] = df["invoice_date"].dt.to_period("M").dt.to_timestamp()

    df = df.reset_index(drop=True)

    print("Cleaning report")
    print("-" * 46)
    prev = report["start"]
    for stage, n in report.items():
        if stage == "start":
            print(f"  {stage:<18} {n:>8,}")
        else:
            print(f"  {stage:<18} {n:>8,}   ({n - prev:+,})")
        prev = n
    kept = len(df) / report["start"] * 100
    print("-" * 46)
    print(f"  kept {len(df):,} rows ({kept:.1f}% of raw), quantity cap = {cap:.0f}")
    return df


if __name__ == "__main__":
    raw = load(RAW)
    out = clean(raw)
    out.to_parquet(OUT, index=False)
    print(f"\nWrote {OUT}  —  {out['stock_code'].nunique()} products, "
          f"{out['month'].nunique()} months")
